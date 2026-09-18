# Inventory Auth

Inventory có hệ thống xác thực riêng tại `/api/v1/inventory-auth`. Dùng lại các bảng users, roles, permissions, user_roles, role_permissions và audit_logs. Không có bảng, DDL, migration hoặc user production mới. Auth/Sales của Người 1 không bị sửa.

## Cấu hình

Đặt qua environment của tiến trình backend, theo `backend/.env.example`:

~~~dotenv
INVENTORY_JWT_SECRET_KEY=
INVENTORY_JWT_ALGORITHM=HS256
INVENTORY_ACCESS_TOKEN_EXPIRE_MINUTES=480
~~~

- Secret cần ít nhất 32 byte ngẫu nhiên và phải khác JWT_SECRET_KEY. Không có secret mặc định hoặc fallback sang Sales. Không đưa secret vào Git.
- Hiện chỉ chấp nhận HS256. Thuật toán lấy từ cấu hình cố định, không lấy từ token header.
- TTL từ 1 đến 1440 phút, mặc định 480. Thiếu/sai cấu hình: login/token validation trả 503; status trả configured=false.
- Test vô hiệu dotenv và DATABASE_URL trước khi import app. Nhiệm vụ này không đọc hoặc sửa .env; chỉ cập nhật .env.example.
- Khởi động production không tự tạo tài khoản, seed hoặc thay schema. Tài khoản cần hash bcrypt hợp lệ và được gán quyền qua quy trình quản trị hiện có.

## Endpoint và response

Mọi response giữ envelope `{success,message,data}`.

| Endpoint | Yêu cầu | data |
| --- | --- | --- |
| POST /inventory-auth/login | JSON username/password | access_token, token_type=bearer, expires_in (giây), user |
| GET /inventory-auth/me | Inventory Bearer, user ACTIVE | user |
| POST /inventory-auth/logout | Inventory Bearer, user ACTIVE | stateless=true |
| GET /inventory-auth/status | Công khai, không truy cập DB | implemented=true, configured |

User response:

~~~json
{
  "user_id": 1,
  "username": "username",
  "full_name": "Tên người dùng",
  "roles": [{"role_code": "WAREHOUSE", "role_name": "Nhân viên kho"}],
  "permissions": ["INVENTORY_MANAGE"]
}
~~~

Đây là shape minh họa contract, không phải tài khoản mặc định. Adapter frontend chuyển sang userId/displayName/roles.code/roles.name để giữ giao diện đã có.

Login nạp user theo username, dùng bcrypt.checkpw cho hash bcrypt hiện hữu từ pgcrypto crypt(..., gen_salt('bf', 10)). Sai password, username không tồn tại, user INACTIVE/LOCKED đều trả 401 với cùng thông báo. User hợp lệ nhưng thiếu quyền vào Kho trả 403. Không ghi password/hash/token vào audit hoặc log. Password dài quá 72 byte UTF-8 hoặc chứa NUL bị từ chối; không tự thay đổi thuật toán hoặc cắt mật khẩu.

Login và logout thành công ghi INVENTORY_LOGIN/INVENTORY_LOGOUT vào audit_logs, cùng actor và địa chỉ client hợp lệ; login cập nhật last_login_at. Lỗi lưu audit/database trả 503, không trả thông tin driver nội bộ.

## JWT và cập nhật quyền

JWT có sub=user_id dạng string, aud=inventory, iss=restaurant-management/inventory-auth, iat, exp, jti. PyJWT kiểm tra chữ ký, algorithm, issuer, audience chính xác, thời hạn và các claim bắt buộc. JWT không mang bản sao roles/permissions.

Mỗi request xác minh token rồi truy vấn lại user/status, role đang active và permission từ DB. Khóa user sau login khiến request tiếp theo trả 401; thu hồi role/permission khiến API nghiệp vụ trả 403. Không có bypass theo tên ADMIN. ADMIN có quyền theo role_permissions đã cấp, giống các role khác.

GET /me vẫn trả danh tính/quyền hiện tại cho user ACTIVE khi quyền Kho vừa bị thu hồi, để frontend render 403 đúng và cho logout. API nghiệp vụ luôn gọi require_inventory_access trước permission cụ thể. Logout cũng cho user ACTIVE đã bị thu hồi quyền Kho thoát phiên.

Token Sales sai key/audience/issuer bị từ chối tại Kho. Sales hiện chưa có JWT dependency và API Sales vẫn là scaffold/public: chưa thể xác minh việc từ chối token Kho bằng endpoint Sales thật. Test kiểm tra token Kho không hợp lệ với audience Sales; không thêm dependency hoặc thay hành vi Sales.

## Permission policy và router được bảo vệ

Quyền vào Kho: ít nhất một trong INVENTORY_MANAGE, PURCHASE_MANAGE, PURCHASE_APPROVE, RECIPE_MANAGE. REPORT_VIEW đứng riêng không đủ: DDL cũng cấp nó cho CASHIER/DATA_ANALYST.

| Router / nghiệp vụ | Đọc | Ghi |
| --- | --- | --- |
| inventory/router.py: units, conversions, ingredients | Quyền vào Kho | INVENTORY_MANAGE |
| inventory/stock_router.py: stock, lots, movements | INVENTORY_MANAGE / PURCHASE_MANAGE / PURCHASE_APPROVE / REPORT_VIEW, và quyền vào Kho | INVENTORY_MANAGE |
| inventory/stocktake_router.py: stocktakes | INVENTORY_MANAGE | INVENTORY_MANAGE |
| purchasing/router.py: suppliers, mappings | INVENTORY_MANAGE / PURCHASE_MANAGE / PURCHASE_APPROVE | PURCHASE_MANAGE |
| purchasing/order_router.py: PO | Như suppliers | Tạo/sửa/gửi/đặt: PURCHASE_MANAGE; duyệt: PURCHASE_APPROVE; hủy: một trong hai |
| purchasing/receipt_router.py: receipts | Như suppliers | INVENTORY_MANAGE |
| recipes/router.py | RECIPE_MANAGE | RECIPE_MANAGE |

Thiếu/sai token trả 401 trước validation payload; thiếu quyền trả 403 trước truy cập nghiệp vụ. Không thay state machine/status/constraint.

Quyền hiện hữu còn thô: INVENTORY_MANAGE gộp nhập/xuất/điều chỉnh/kiểm kê; RECIPE_MANAGE gộp sửa/kích hoạt. MANAGER trong DDL có PURCHASE_APPROVE/RECIPE_MANAGE/REPORT_VIEW nhưng chưa có INVENTORY_MANAGE/PURCHASE_MANAGE; muốn ghi tồn/lập đơn cần được cấp thêm qua quản trị. WAREHOUSE hiện có cả INVENTORY_MANAGE và PURCHASE_MANAGE. Không tự nâng quyền theo role, thêm permission production hoặc sửa seed.

## Actor do server gán

Các request legacy giữ actor field bắt buộc để tương thích schema/service, nhưng router bỏ qua giá trị client:

- Stock issue/adjust: performed_by.
- PO create: created_by; chuyển trạng thái: actor_id, từ đó approved_by.
- Receipt create: received_by.
- Stocktake create/complete: created_by/completed_by.
- Recipe create: created_by được router truyền riêng; body không được phép chứa field này.
- Receipt confirm: movement.performed_by là người xác nhận hiện tại; received_by vẫn là người lập phiếu.

Frontend hiển thị tên session và không có ô nhập actor ID. Service nhận ID đã xác thực từ router. Các hàm service nội bộ dùng cho Sales giữ signature cũ; tham số actor bổ sung có default để không phá caller nội bộ. Không có field user tùy ý cho hành động mới.

## Session frontend và logout stateless

- Adapter production gọi login rồi /me; lưu token tại sessionStorage.inventory_access_token sau khi /me hợp lệ.
- Refresh đọc đúng key này và gọi /me trước mount trang. Không dùng token/session của Sales.
- Axios nghiệp vụ chỉ gắn token cho đường dẫn /api/v1/inventory, /purchasing, /recipes; Auth client riêng chỉ gửi Bearer cho /me và /logout.
- 401 xóa phiên, về /inventory/login; 403 nghiệp vụ hiện trang từ chối đúng route phát sinh request. Response của phiên/trang cũ không phá phiên/trang mới.
- Logout xóa storage ngay và gọi endpoint bằng token đã chụp trước khi xóa. Dù request thất bại, client vẫn thoát. Logout cũ hoàn tất không xóa phiên mới.
- Không có blacklist/session table: JWT vẫn có thể được dùng tới exp nếu user/quyền còn hợp lệ. Không tuyên bố server thu hồi token.
- ReturnTo chỉ nhận đường dẫn nội bộ /inventory. Layout không có Sales.
- sessionStorage vẫn có thể bị đọc khi có XSS; triển khai bằng HTTPS và duy trì bảo vệ XSS/CSP. Giới hạn tần suất login nên cấu hình tại reverse proxy; hiện không có distributed rate limiter.

## Kiểm thử và giới hạn

Backend tests dùng SQLite clone metadata: bcrypt thật, JWT thật, bảng RBAC/audit thật; không override Auth trong test_inventory_auth hoặc các stock/workflow tests. Ba bộ test cũ chuyên biệt cho serialization/service catalog/supplier/recipe có principal fixture riêng để giữ kiểm tra truy vấn và fake repository; tests bảo mật mới kiểm tra lớp Auth thật cho mọi nhóm router.

E2E dùng production adapter qua cấu hình test frontend 5174 và API SQLite 8011. Không còn alias/mockAuthAdapter. Mỗi test đăng nhập thật, kể cả APIRequestContext chuẩn bị chứng từ. Fixtures manager/warehouse/purchaser/sales/locked chỉ tồn tại trong SQLite bộ nhớ. Secret test sinh ngẫu nhiên lúc khởi động; không có user production tạo tự động.

Một bài UI 403 chuyển request tới endpoint thật thiếu quyền để server phát 403; không mock response Auth. Unit/component tests vẫn mock HTTP/adapter để kiểm tra lỗi và race độc lập.

Chưa kiểm chứng PostgreSQL/Neon row locking, deployment production, hash/tài khoản thật trên Neon hoặc Auth của Sales. Tìm món, Sales gọi consume_in_transaction và audit nghiệp vụ toàn hệ thống vẫn là dependency liên module. Audit login/logout Kho đã hoạt động.

Nguồn thư viện: [PyJWT API](https://pyjwt.readthedocs.io/en/stable/api.html), [bcrypt](https://github.com/pyca/bcrypt). Dependencies tối thiểu thêm: PyJWT>=2.10.1,<3 và bcrypt>=5,<6.
