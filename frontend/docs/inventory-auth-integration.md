# Tích hợp Inventory Auth thật

Inventory dùng Auth riêng tại `/api/v1/inventory-auth`, JWT/secret/audience/session độc lập với Sales và dùng lại bảng RBAC/audit hiện hữu. Adapter production đã nối login, me, logout và status; không còn chờ Auth của Người 1.

Xem [contract và permission phía backend](../../backend/docs/inventory-auth.md) để biết cấu hình, payload, actor, các router bảo vệ và giới hạn. Xem [checkpoint](inventory-ui-progress.md) cho kết quả lệnh đã chạy.

## Truy cập

- `/inventory/login`: form username/password. Không chọn role, không đăng nhập bằng employee ID.
- `/inventory/*`: guard session và capability trước mount; logo/menu chỉ thuộc Kho.
- Secret Inventory chưa cấu hình: status báo configured=false và form báo cần quản trị cấu hình. Khi backend đã cấu hình, form hoạt động với user thật có quyền.
- Login POST /inventory-auth/login, sau đó GET /inventory-auth/me để lấy quyền hiện tại.
- Storage key riêng: `inventory_access_token` trong sessionStorage. Refresh gọi /me; không dùng storage Sales.
- Logout xóa storage ngay và gọi server; server ghi audit nhưng JWT vẫn hợp lệ tới hạn vì không có blacklist/session table.
- 401 xóa session/về login. 403 hiển thị từ chối trong Kho; request cũ không khóa nhầm trang mới.
- ReturnTo chỉ nhận URL Kho nội bộ an toàn.

## Quyền

Ưu tiên permission trong database, không tự cấp theo role. Quyền vào Kho cần INVENTORY_MANAGE, PURCHASE_MANAGE, PURCHASE_APPROVE hoặc RECIPE_MANAGE. REPORT_VIEW đứng riêng không đủ vì cũng được cấp cho thu ngân.

Mapping capability frontend đồng bộ policy server: quản lý tồn/receipt/stocktake dùng INVENTORY_MANAGE; lập đơn/supplier dùng PURCHASE_MANAGE; duyệt đơn dùng PURCHASE_APPROVE; công thức dùng RECIPE_MANAGE; báo cáo cần REPORT_VIEW kèm quyền vào Kho. Quyền đọc dữ liệu tham chiếu phù hợp từng nhóm.

Các quyền thô chưa tách xuất/điều chỉnh/chốt hoặc sửa/kích hoạt. MANAGER muốn ghi tồn phải có INVENTORY_MANAGE trong DB; không tự nâng quyền hoặc sửa seed.

## Attribution

Không có ô nhập actor. Frontend gửi current user để tương thích payload cũ; backend luôn thay actor bằng người đã xác thực. Recipe creator và movement khi xác nhận receipt cũng do server gán. Phía server mới là nơi ngăn client gửi ID người khác.

## Chạy E2E cô lập

~~~powershell
# Repository root, Python có backend requirements
python frontend/e2e/demo_api.py

# frontend, terminal khác
npm.cmd run dev -- --config e2e/vite.config.ts
npm.cmd run test:e2e
~~~

Frontend test 5174 proxy cố định đến SQLite 8011, không đọc .env. Không alias adapter, không mock login/me/JWT. Marker yêu cầu `auth=inventory-real-backend`; không chạy trên Neon/server thật. Bản normal Vite vẫn dùng API cấu hình bởi môi trường của ứng dụng.

Unit tests vẫn mock adapter/HTTP để kiểm tra failure/race. E2E login dùng bcrypt và JWT thật trên SQLite, chưa phải xác minh deployment hoặc dữ liệu Neon.

## Phụ thuộc còn lại

Sales Auth/token rejection qua endpoint Sales thật chưa thể kiểm chứng vì Sales còn public/scaffold. API tìm món, tích hợp Sales tiêu hao nguyên liệu, audit nghiệp vụ chung và PostgreSQL concurrency vẫn cần công việc liên module. Không còn blocker Auth backend đối với riêng Kho.
