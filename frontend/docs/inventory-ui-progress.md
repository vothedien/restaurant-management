# Checkpoint Inventory Auth thật

Cập nhật: 18/09/2026. Hoàn thành backend Inventory Auth riêng và nối frontend Kho hiện hữu. Kiểm chứng bằng SQLite cô lập; không kết nối Neon.

## A. File backend/frontend

- Thêm `backend/app/modules/inventory_auth/`: router, schemas, service, repository, dependencies, security và package initializer.
- Cập nhật `backend/app/core/config.py`, `backend/app/api/router.py`, `.env.example`, requirements và README. Thêm PyJWT/bcrypt; không đọc hoặc sửa `.env`.
- Bảo vệ 7 router inventory/stock/stocktake/suppliers/orders/receipts/recipes; cập nhật receipt/recipe service để nhận actor đã xác thực. Không thay state machine, model hoặc DDL.
- Thêm `backend/tests/inventory_auth_fixtures.py`, `test_inventory_auth.py`; cập nhật fixture và các test nghiệp vụ hiện hữu để dùng xác thực thật hoặc principal fixture chuyên biệt.
- Nối `frontend/src/features/inventory/auth/backendAdapter.ts`; cập nhật transport, permission mapping, login và các test liên quan. Thêm `backendAdapter.test.ts`.
- E2E dùng adapter production và Inventory Auth thật; xóa `e2e/mockAuthAdapter.ts`, cập nhật test server/config/session/specs.
- Cập nhật tài liệu UI/API/purchasing/Auth. Giữ các thay đổi frontend đã có; không viết lại trang nghiệp vụ hoặc sửa Auth/Sales của Người 1.

## B. Cách Inventory Auth hoạt động

Dùng các bảng users, roles, permissions, user_roles, role_permissions và audit_logs hiện hữu. Login xác minh bcrypt, trạng thái ACTIVE và quyền vào Kho. Sai username/password hoặc tài khoản bị khóa nhận cùng lỗi 401; tài khoản hợp lệ chỉ có Sales nhận 403.

JWT dùng secret riêng, HS256, audience `inventory`, issuer `restaurant-management/inventory-auth` và các claim sub/iat/exp/jti. Secret tối thiểu 32 byte, khác secret Sales; thiếu cấu hình không phát token. Mỗi request đọc lại trạng thái, roles và permissions trong DB. Khóa tài khoản/thu hồi quyền có hiệu lực ở request tiếp theo.

Frontend lưu token trong sessionStorage với key `inventory_access_token`, khôi phục qua /me và chỉ gửi Bearer cho API Kho. Login/refresh/logout, 401/403, returnTo nội bộ, menu/nút theo permission và layout riêng đều được kiểm tra. Server gán actor từ user đã xác thực, bỏ qua ID legacy do client gửi.

Login/logout ghi audit. Logout xóa phiên client nhưng không thu hồi JWT trên server; token còn dùng được tới exp nếu tài khoản/quyền vẫn hợp lệ.

## C. Endpoint và permission

Bốn endpoint dưới `/api/v1/inventory-auth`: POST login, GET me, POST logout, GET status. Contract và ma trận quyền đầy đủ: [Inventory Auth backend](../../backend/docs/inventory-auth.md).

| Nhóm | Quyền chính |
| --- | --- |
| Danh mục Kho | Đọc: quyền vào Kho; ghi: INVENTORY_MANAGE |
| Tồn/lô/biến động | Đọc: quyền phù hợp Kho/mua hàng/báo cáo kèm quyền vào Kho; ghi: INVENTORY_MANAGE |
| Kiểm kê, ghi phiếu nhập | INVENTORY_MANAGE |
| Nhà cung cấp, lập/sửa/gửi/đặt PO | PURCHASE_MANAGE |
| Duyệt PO | PURCHASE_APPROVE |
| Hủy PO | PURCHASE_MANAGE hoặc PURCHASE_APPROVE |
| Công thức | RECIPE_MANAGE |

REPORT_VIEW đơn lẻ không cho vào Kho vì seed cũng cấp quyền đó cho thu ngân. Không cấp quyền theo chuỗi tên ADMIN/MANAGER. `/me` vẫn trả quyền hiện tại cho user ACTIVE vừa bị thu hồi quyền Kho; API nghiệp vụ trả 403 và frontend hiển thị đúng trạng thái từ chối.

## D. Kết quả lệnh kiểm thử

Python sử dụng runtime sẵn có tại `tmp/runtime/python311/python.exe`, với dependencies backend. Không dùng database URL hoặc dotenv production trong test.

| Lệnh thực tế | Kết quả |
| --- | --- |
| Root: `.\tmp\runtime\python311\python.exe -m ruff check backend` | PASS |
| Root: `.\tmp\runtime\python311\python.exe -m ruff format --check backend` | PASS, 103 files |
| Backend: `..\tmp\runtime\python311\python.exe -m pytest` | PASS, 423 tests, 205,19 giây |
| Frontend: `npm.cmd run lint` | PASS |
| Frontend: `npm.cmd run typecheck` | PASS |
| Frontend: `npm.cmd run test` | PASS, 107 tests / 13 files |
| Frontend: `npm.cmd run build` | PASS, 134 modules |
| Frontend: `npm.cmd run test:e2e -- --output=../tmp/inventory-real-auth-playwright-20260917` | PASS, 16 tests, 4,4 phút |
| Kiểm tra TypeScript riêng cho e2e/*.ts và playwright.config.ts | PASS |
| `git diff --check` | PASS; chỉ có cảnh báo chuẩn hóa LF/CRLF |

Backend có 4 warning: hai deprecation từ thư viện, một cảnh báo relationship RBAC hiện hữu và một lỗi quyền ghi cache pytest. Không có test fail. Không sửa model của Người 1 để xử lý warning.

42 test Inventory Auth bao phủ bcrypt/JWT thật, audit, tài khoản thiếu quyền/bị khóa, thiếu/hết hạn/sai audience token, thu hồi quyền/role, toàn bộ route được bảo vệ và chống giả mạo actor. Các workflow tests còn lại kiểm tra không thay đổi nghiệp vụ.

E2E gồm 10 kịch bản Auth và 6 kịch bản nghiệp vụ/smoke, dùng production adapter trên frontend 5174 và SQLite bộ nhớ 8011 có marker xác nhận môi trường. Không mock login/me/JWT. Bài UI 403 chuyển request đến endpoint thật thiếu quyền để nhận lỗi server thật. Sau E2E, thay đổi nhỏ giới hạn mọi capability theo quyền vào Kho được kiểm tra lại bằng toàn bộ lint/typecheck/unit/build; không lặp các E2E với tài khoản hợp lệ không bị ảnh hưởng.

Visual QA đăng nhập thật ở 375/1440 px, menu nhân viên kho trên mobile, không Sales, không tràn ngang hoặc lỗi JavaScript. Bộ E2E giữ các kích thước responsive và luồng Kho cũ. Screenshot/report nằm trong `tmp/` ignored. Bản build không chứa fixture, mật khẩu test hoặc origin test.

Sau kiểm thử, đã xác minh và dừng đúng API SQLite 8011 và Vite test 5174 do phiên này khởi động. Vite thông thường không bị dừng.

## E. Giới hạn còn lại

1. Logout stateless: không có bảng session/blacklist và không tuyên bố token đã bị thu hồi.
2. Quyền hiện hữu còn thô. MANAGER trong seed chưa có INVENTORY_MANAGE/PURCHASE_MANAGE; muốn ghi tồn/lập đơn cần được quản trị cấp quyền. Không tự sửa seed/Neon.
3. Sales hiện chưa có JWT dependency và còn public/scaffold. Đã kiểm tra token Kho không hợp lệ với audience Sales, nhưng chưa thể kiểm chứng endpoint Sales từ chối token này. Không sửa Auth/Sales.
4. Chưa kiểm chứng deployment, tài khoản/hash production hoặc PostgreSQL locking/concurrency. Cần cấu hình secret riêng trước khi dùng môi trường thật; không tạo user production tự động.
5. API tìm món, Sales gọi tiêu hao nguyên liệu và audit nghiệp vụ chung vẫn là công việc liên module. Audit login/logout Kho đã có.
6. Các giới hạn báo cáo và constraint nghiệp vụ cũ giữ nguyên; không mở rộng nhiệm vụ sang forecast/AI.

## F. Git status

Branch vẫn là `feature/inventory-frontend`. Giữ nguyên index có 88 paths đã staged từ trước (6 sửa, 82 thêm); không stage/commit/push/PR, switch/pull/merge/rebase/reset. Các chỉnh sửa mới ở working tree và các file Auth mới còn untracked. `AD frontend/e2e/mockAuthAdapter.ts` là xóa adapter mock đã staged trước đó theo yêu cầu thay bằng backend thật.

Output đầy đủ của `git status -sb` và danh sách file được lưu cùng báo cáo Git cuối trong `tmp/inventory-auth-final-git-report.txt` tại workspace, không đưa artifact vào Git.

## G. Git diff stat

`git diff --stat` so sánh working tree với index; không đếm toàn bộ frontend đã staged hoặc các file Inventory Auth mới chưa tracked. Xem snapshot cuối trong báo cáo Git nói trên, cùng thống kê staged riêng để tránh hiểu nhầm phạm vi.

## H. Git diff check và kết luận

`git diff --check` đạt. Kiểm tra thêm index và whitespace của file mới; không phát hiện secret/artifact thừa trong các paths thay đổi. Không có thay đổi Auth/Sales, model hoặc migration trong phần triển khai mới.

~~~text
READY_TO_COMMIT: YES
INVENTORY_AUTH_REAL_BACKEND: YES
NEON_TOUCHED: NO
MIGRATION_CREATED: NO
~~~

READY_TO_COMMIT áp dụng cho mã nguồn và các kiểm thử đã nêu, không khẳng định deployment production đã được xác minh. Người dùng tự xem xét và thực hiện Git.
