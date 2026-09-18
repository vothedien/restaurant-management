# Hợp đồng API — Danh mục kho

Đối chiếu trực tiếp router, Pydantic schemas, service, repository và các test backend trong nhánh nền `develop`. Đây là phần danh mục của module frontend; mua hàng, nhập hàng, tồn và kiểm kê được mô tả trong `inventory-ui.md` và `backend/docs/inventory-workflows.md`.

## Quy ước

- Prefix HTTP thực: `/api/v1`. Ví dụ `/inventory/ingredients` bên dưới tương ứng `/api/v1/inventory/ingredients`.
- Response thành công: `{success, message, data}`. HTTP client frontend lấy `.data.data`; không truy cập Neon trực tiếp.
- Trang danh sách: `{items, total, limit, offset}`; `limit` 1–100, mặc định 20; `offset >= 0`. Frontend dùng `page` trên URL rồi gửi `limit=20`, `offset=(page-1)*20`. Không gửi tham số `page` cho backend.
- Decimal truyền bằng chuỗi JSON. Số lượng: tối đa 14 chữ số tổng, 3 chữ số thập phân. Giá mua: 14/2. Hệ số quy đổi đơn vị: 18/6. Form chấp nhận dấu phẩy thập phân, chuẩn hóa thành dấu chấm khi gửi.
- Ngày hiệu lực là `YYYY-MM-DD`, giữ nguyên date-only. Timestamp được hiển thị tại `Asia/Ho_Chi_Minh`.
- Mã lỗi chung: `400` vi phạm nghiệp vụ; `404` không tìm thấy; `409` trùng mã/liên kết hoặc xung đột trạng thái; `422` request không hợp lệ; `503` lỗi lưu trữ đã được backend che thông tin nội bộ. Frontend cũng xử lý `401`, `403`, lỗi máy chủ và lỗi mạng theo lớp lỗi dùng chung.
- Mutation không retry tự động và không optimistic update. `useMutation` chặn gửi kép, hiển thị lỗi tại form, giữ dữ liệu nhập. Mutation thành công phát sự kiện để các query kho đang mở refresh; query có AbortController và không hiển thị kết quả tìm kiếm cũ.
- Bộ chọn đơn vị và quy đổi thu thập các trang của danh mục tham chiếu, giới hạn tối đa 1.000 mục và báo lỗi rõ nếu vượt. Bộ chọn nguyên liệu tìm kiếm phía server, tối đa 100 kết quả mỗi lần và hướng dẫn thu hẹp tìm kiếm nếu còn kết quả. Không tải toàn bộ lịch sử giao dịch.

## 1. Nguyên liệu

Routes giao diện: `/inventory/ingredients`, `/inventory/ingredients/:id`.

| Method | Endpoint | Query / request | Response / hành vi |
| --- | --- | --- | --- |
| GET | `/inventory/ingredients` | `limit`, `offset`, `search` tối đa 150 ký tự, `status=ACTIVE/INACTIVE` | Trang `IngredientRead`, kèm `base_unit` |
| GET | `/inventory/ingredients/{id}` | ID nguyên liệu | `IngredientRead` |
| POST | `/inventory/ingredients` | `IngredientCreate` | 201; nguyên liệu mới |
| PATCH | `/inventory/ingredients/{id}` | Các field cập nhật của `IngredientUpdate` | Nguyên liệu đã lưu |
| DELETE | `/inventory/ingredients/{id}` | Không có body | Đổi trạng thái thành `INACTIVE`; giữ bản ghi và lịch sử |
| GET | `/inventory/stock` | `ingredient_id`, `limit`, `offset` | Chi tiết dùng tổng tồn, tồn khả dụng, tồn chưa khả dụng |
| GET | `/purchasing/supplier-ingredients` | `ingredient_id`, `limit`, `offset` | Tab nhà cung cấp liên kết |

`IngredientCreate`: `ingredient_code` 1–40 ký tự, `ingredient_name` 1–150, `base_unit_id > 0`, `manages_lot` boolean, `default_shelf_life_days` integer >= 0 hoặc null, `minimum_stock_qty` và `safety_stock_qty` decimal >= 0, `status`. Response bổ sung `ingredient_id`, `created_at`, `updated_at`, `base_unit`.

Quy tắc đã áp dụng:

- Đơn vị cơ sở cần hoạt động. Backend chuẩn hóa mã thành chữ hoa và bỏ khoảng trắng.
- Không đổi đơn vị cơ sở sau khi có `recipe_items`, `supplier_ingredients`, `stock_lots` hoặc `stock_movements` tham chiếu. API không trả cờ `has_references`; form giải thích giới hạn và giữ dữ liệu nếu server trả 409.
- `DELETE` là ngừng hoạt động. Nguyên liệu không được dùng trong nghiệp vụ mới; tồn/lịch sử vẫn xem được.
- Danh sách không làm N+1 để tính tồn, số nhà cung cấp hay hạn gần nhất. Chi tiết tải riêng số dư; các liên kết “Tồn theo lô”, “Biến động kho”, “Xuất / điều chỉnh” giữ `ingredient_id` trong URL.
- Sau lưu/ngừng dùng: refresh danh sách/chi tiết, số dư, bộ chọn và mapping đang mở.

## 2. Đơn vị và quy đổi

Route giao diện: `/inventory/units`, tab quy đổi dùng `?tab=conversions`.

| Method | Endpoint | Query / request | Response / hành vi |
| --- | --- | --- | --- |
| GET | `/inventory/units` | `limit`, `offset`, `search` <= 80 | Trang `UnitRead` |
| GET | `/inventory/units/{id}` | ID | `UnitRead` |
| POST | `/inventory/units` | `unit_code`, `unit_name`, `dimension`, `is_active` | 201; đơn vị mới |
| PATCH | `/inventory/units/{id}` | Các field đơn vị | Đơn vị đã lưu |
| DELETE | `/inventory/units/{id}` | Không có body | `is_active=false` |
| GET | `/inventory/unit-conversions` | `limit`, `offset` | Trang `UnitConversionRead`, kèm đơn vị nguồn/đích |
| GET | `/inventory/unit-conversions/{id}` | ID | `UnitConversionRead` |
| POST | `/inventory/unit-conversions` | `from_unit_id`, `to_unit_id`, `factor` | 201; quy đổi mới |
| PATCH | `/inventory/unit-conversions/{id}` | Nguồn/đích/hệ số cần đổi | Quy đổi đã lưu |
| DELETE | `/inventory/unit-conversions/{id}` | Không có body | Xóa quy đổi, response `{conversion_id}` |

`UnitRead`: `unit_id`, `unit_code` <= 20 ký tự, `unit_name` <= 80, `dimension=MASS/VOLUME/COUNT/LENGTH/OTHER`, `is_active`. Không có field ký hiệu riêng; UI dùng mã đơn vị.

Quy tắc:

- Nhóm đơn vị `dimension` bất biến sau khi tạo; form khóa trường này khi sửa.
- Nguồn và đích phải khác nhau, đang hoạt động và cùng `dimension`. Cặp có hướng nguồn/đích là duy nhất. Hệ số là decimal dương, tối đa 6 số thập phân.
- Chỉ quy đổi trực tiếp một chiều; không tự đảo hay tìm đường qua các đơn vị trung gian.
- Xóa quy đổi là xóa thật, cần xác nhận và giải thích ảnh hưởng tới thao tác mới. Định lượng/chứng từ đã lưu là snapshot.
- Backend không kiểm tra vòng quy đổi hay tính nhất quán toàn graph; UI không giả lập kiểm tra này.
- Sau mutation: refresh đơn vị/quy đổi và các bộ chọn tương ứng.

## 3. Công thức

Routes giao diện: `/inventory/recipes`, `/inventory/recipes/:dishId`; chọn phiên bản bằng `?version=<recipe_version_id>`.

| Method | Endpoint | Query / request | Response / hành vi |
| --- | --- | --- | --- |
| GET | `/recipes` | `dish_id > 0`, `status`, `limit`, `offset` | Trang `RecipeRead`, mỗi dòng là một phiên bản với `dish` summary |
| GET | `/recipes/{recipe_version_id}` | ID phiên bản | `RecipeDetail` gồm `items` |
| GET | `/recipes/dishes/{dish_id}/active` | ID món | Bản ACTIVE đang trong khoảng hiệu lực; 404 nếu chưa có bản đủ hiệu lực |
| POST | `/recipes` | `dish_id`, `effective_from`, `effective_to`, `notes` | 201; tạo DRAFT, số phiên bản do server cấp |
| PATCH | `/recipes/{id}` | Chỉ `effective_from`, `effective_to`, `notes` | Sửa metadata của bản DRAFT |
| PUT | `/recipes/{id}/items` | `{items:[{ingredient_id,unit_id,quantity}]}` | Thay toàn bộ định lượng trong một transaction |
| POST | `/recipes/{id}/activate` | Không body | Kích hoạt DRAFT; các bản ACTIVE cũ thành INACTIVE trong cùng transaction |

`RecipeStatus`: `DRAFT`, `ACTIVE`, `INACTIVE`, `EXPIRED`. `RecipeRead` gồm `recipe_version_id`, `dish_id`, `version_no`, trạng thái, ngày hiệu lực, ghi chú, người tạo nullable, ngày tạo và dish summary. `RecipeItemRead` bổ sung `base_quantity`, thông tin nguyên liệu và đơn vị.

Quy tắc:

- Chỉ tạo/kích hoạt cho món `ACTIVE`. Không có API chọn danh mục món hiện tại: frontend dùng ID món đang tồn tại, nêu rõ hướng dẫn. Trang danh sách hiển thị phiên bản thật từ API, không suy luận món chưa có công thức.
- Bản lịch sử chỉ đọc. DRAFT mới được sửa metadata/định lượng/kích hoạt. Backend từ chối các field server sở hữu.
- Công thức cần ít nhất 1 dòng khi lưu định lượng hoặc kích hoạt; nguyên liệu không trùng nhau, đang hoạt động, quantity > 0.
- Đơn vị và đơn vị cơ sở phải hoạt động/cùng nhóm. Dùng đơn vị cơ sở hoặc conversion trực tiếp từ đơn vị dòng sang đơn vị cơ sở.
- Base quantity được nhân bằng decimal và làm tròn `ROUND_HALF_UP` tới 0.001; phải trong khoảng `0 < base_quantity <= 99999999999.999`. UI xem trước theo cùng quy tắc và dùng `base_quantity` từ response khi hiển thị dữ liệu đã lưu.
- Ngày kết thúc không trước ngày bắt đầu. Bỏ ngày bắt đầu khi kích hoạt thì server dùng ngày hiện tại. Kích hoạt bản có ngày bắt đầu ở tương lai vẫn ngừng bản ACTIVE cũ ngay; hộp xác nhận giải thích khoảng trống hiệu lực có thể xảy ra.
- Chỉ mở một editor có unsaved guard tại một thời điểm. Chuyển phiên bản bằng query string cũng được cảnh báo nếu chưa lưu. Sau tạo, đóng form trước khi chọn phiên bản để không hỏi bỏ dữ liệu đã lưu.
- Sau save/activate: refresh chi tiết và danh sách phiên bản của món; không tự kích hoạt sau khi lưu định lượng.
- Chưa hiển thị chi phí công thức vì API chưa quy định nguồn giá phù hợp.

## 4. Nhà cung cấp và liên kết nguyên liệu

Routes giao diện: `/inventory/suppliers`, `/inventory/suppliers/:id`.

| Method | Endpoint | Query / request | Response / hành vi |
| --- | --- | --- | --- |
| GET | `/purchasing/suppliers` | `search` <= 180, `status`, `limit`, `offset` | Trang `SupplierRead` |
| GET | `/purchasing/suppliers/{id}` | ID | `SupplierRead` |
| POST | `/purchasing/suppliers` | `SupplierCreate` | 201; tạo nhà cung cấp |
| PATCH | `/purchasing/suppliers/{id}` | Các field `SupplierUpdate` | Nhà cung cấp đã lưu |
| DELETE | `/purchasing/suppliers/{id}` | Không body | Ngừng supplier và tất cả mapping của supplier |
| GET | `/purchasing/supplier-ingredients` | `supplier_id`, `ingredient_id`, `is_active`, `is_preferred`, `limit`, `offset` | Trang mapping kèm supplier/ingredient/purchase_unit summary |
| GET | `/purchasing/supplier-ingredients/{id}` | ID mapping | `SupplierIngredientRead` |
| POST | `/purchasing/supplier-ingredients` | `SupplierIngredientCreate` | 201; liên kết mới |
| PATCH | `/purchasing/supplier-ingredients/{id}` | Các field mapping trừ `supplier_id`, `ingredient_id` | Mapping đã lưu |
| DELETE | `/purchasing/supplier-ingredients/{id}` | Không body | `is_active=false`, `is_preferred=false` |

`SupplierCreate`: `supplier_code` 1–40, `supplier_name` 1–180, `contact_name` <=120 hoặc null, `phone` <=20 hoặc null, `email` <=150 hoặc null, `address` nullable, `tax_code` <=30 hoặc null, `status=ACTIVE/INACTIVE/SUSPENDED`. Response bổ sung ID và timestamp. Tìm kiếm hỗ trợ mã/tên/người liên hệ/điện thoại/email.

`SupplierIngredientCreate`: `supplier_id`, `ingredient_id`, `supplier_sku` <=80 hoặc null, `purchase_unit_id`, `base_qty_per_purchase_unit > 0`, `lead_time_days >= 0`, `minimum_order_qty > 0`, `latest_unit_price >= 0` hoặc null, `is_preferred`, `is_active`. Field số ngày tối đa 2147483647. Mức đặt tối thiểu mặc định 1; giá null khác giá 0.

Quy tắc:

- Mã supplier duy nhất. Tạo mapping cần supplier/nguyên liệu/đơn vị mua hoạt động; cặp supplier/nguyên liệu duy nhất kể cả mapping đã ngừng.
- Không đổi supplier_id hoặc ingredient_id trên mapping đã tạo. Form sửa khóa lựa chọn nguyên liệu và chỉ PATCH field được phép.
- Mapping có thể dùng đơn vị đóng gói khác nhóm đơn vị cơ sở, với hệ số nhập rõ ràng. Không suy luận quy cách từ tên BOX/BAG/... và không lấy conversion chung để áp đặt quy cách đóng gói.
- Mỗi nguyên liệu chỉ có một supplier ưu tiên. Chọn ưu tiên mới gỡ ưu tiên cũ trong transaction backend; UI xác nhận hậu quả và refresh dữ liệu sau thành công.
- Ngừng mapping gỡ ưu tiên. Ngừng supplier (DELETE hoặc PATCH INACTIVE) đồng thời ngừng toàn bộ mapping và gỡ ưu tiên. Kích hoạt lại supplier không tự phục hồi mapping; các liên kết được mở lại riêng.
- `SUSPENDED` là trạng thái backend thật, không phải soft delete và không có cascade giống INACTIVE.
- Chi tiết supplier liên kết đơn mua với `supplier_id`. Không hiển thị lịch sử giá giả: chỉ có `latest_unit_price` của mapping, chưa có endpoint lịch sử giá.
- Sau mutation: refresh supplier, mapping theo supplier/nguyên liệu, danh sách nhà cung cấp và bộ chọn mua hàng đang mở.

## Khoảng trống backend được giữ minh bạch

1. `backend/app/modules/catalog/router.py` chỉ có `/catalog/status`; chưa có danh sách/tìm kiếm/chi tiết món. Chưa thể liệt kê chính xác món chưa có công thức hay nhóm món, cần ID món hợp lệ để tạo phiên bản đầu tiên.
2. Danh sách nguyên liệu chỉ hỗ trợ `search/status`, chưa có lọc theo tồn/đơn vị hoặc aggregate số mapping/hạn gần nhất. UI dẫn sang trang tồn và dùng chi tiết cho dữ liệu bổ sung.
3. Chưa có truy vấn công thức theo nguyên liệu, số nguyên liệu dùng một đơn vị, lịch sử giá supplier hay lần mua gần nhất; không tải chi tiết từng dòng để giả lập các aggregate.
4. Recipe list không trả số nguyên liệu; số lượng này chỉ hiện khi mở RecipeDetail.
5. Không có kiểm tra graph quy đổi. Không có giá chuẩn cho tính giá vốn công thức.
6. Khi đơn vị/quy đổi vượt 1.000 mục, cần bổ sung bộ chọn phân trang/tìm kiếm phù hợp; giao diện báo giới hạn thay vì âm thầm cắt danh sách.
7. Inventory Auth riêng đã xác minh bcrypt/JWT và áp permission cho router; server lấy actor từ authenticated user. Auth/Sales không bị sửa. Xem [contract Auth](inventory-auth-integration.md). E2E đăng nhập thật trên SQLite; unit tests dùng HTTP mock, chưa kiểm chứng Neon.

## Kiểm thử danh mục

- `CatalogForms.test.tsx`: tải/empty/lỗi/retry, decimal string lớn, double submit, validation inline, 409 giữ form, xác nhận bỏ dữ liệu, bản công thức chỉ đọc, xác nhận kích hoạt, chỉ một editor công thức, cảnh báo chuyển phiên bản chưa lưu, từ chối conversion cùng đơn vị, hiển thị đủ 6 chữ số hệ số.
- `CatalogContracts.test.tsx`: page → limit/offset, PUT items và chuỗi decimal, DELETE soft-deactivate supplier/mapping, tải bộ chọn có giới hạn, precision theo schema.
- Các kiểm tra frontend dùng API mock bám schema. Không có request ghi vào Neon, không seed, không migration.
- Kết quả chạy thực tế sau các thay đổi layout/Auth và phân quyền được ghi trong [checkpoint](inventory-ui-progress.md); không dùng số test của lượt triển khai danh mục trước làm kết quả cho phiên bản hiện tại.
- `e2e/catalog-flow.spec.ts` dùng backend SQLite memory có marker xác minh môi trường, kiểm tra tạo bản nháp → thêm FLOUR 0.250 KG → quy đổi 250 đơn vị cơ sở → PUT định lượng → kích hoạt → chỉ đọc sau refresh; kiểm tra overflow tại 390px. Kết quả chạy browser được ghi trong báo cáo chung `inventory-ui.md`.
