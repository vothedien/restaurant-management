# Hợp đồng giao diện mua và nhập hàng

Nguồn xác minh: router, Pydantic schemas, service, repository và test tại `backend/app/modules/purchasing/{order,receipt}_*`, `backend/tests/test_purchase_orders.py`, `backend/tests/test_goods_receipts.py`. Tất cả endpoint dưới đây có prefix `/api/v1`; response được mở từ `data`. Danh sách dùng `{items,total,limit,offset}`, tối đa 100 dòng/trang.

## Route và API

| Route giao diện | Endpoint / method | Query hoặc payload |
| --- | --- | --- |
| `/inventory/purchase-orders` | GET `/purchasing/purchase-orders` | `supplier_id`, `status`, `limit`, `offset`; đồng bộ bộ lọc/phân trang URL |
| `/inventory/purchase-orders/new` | POST `/purchasing/purchase-orders` | `purchase_order_number?`, `supplier_id`, `created_by`, `order_date`, `expected_delivery_date?`, `notes?`, 1–200 `items` |
| `/inventory/purchase-orders/:id/edit` | GET/PATCH `/purchasing/purchase-orders/:id` | PATCH ngày đặt, ngày dự kiến, ghi chú và thay toàn bộ `items`; không thay supplier/mã đơn |
| `/inventory/purchase-orders/:id` | GET `/purchasing/purchase-orders/:id`; POST `/:id/status`; GET `/purchasing/goods-receipts` | Transition `{status,actor_id,cancellation_reason?}`; danh sách phiếu lọc `purchase_order_id` |
| `/inventory/goods-receipts` | GET `/purchasing/goods-receipts` | `purchase_order_id`, `status`, `date_from`, `date_to`, `limit`, `offset` |
| `/inventory/goods-receipts/new` | GET `/purchasing/purchase-orders` | Chọn đơn ORDERED/PARTIALLY_RECEIVED, phân trang máy chủ |
| `/inventory/goods-receipts/new?purchase_order_id=:id` | GET đơn mua; POST `/purchasing/goods-receipts` | `receipt_number?`, `purchase_order_id`, `receipt_date`, `supplier_document_no?`, `received_by`, `notes?`, 1–200 dòng lô |
| `/inventory/goods-receipts/:id` | GET `/purchasing/goods-receipts/:id`; POST `/:id/confirm`; POST `/:id/cancel` | Confirm/cancel không có request body; chỉ hiện hành động đúng trạng thái |

Mỗi dòng đơn mua gửi `{supplier_ingredient_id,ordered_quantity,expected_unit_price}`. Response bổ sung `purchase_order_item_id`, `purchase_unit_id`, `base_qty_per_purchase_unit`, `ordered_base_qty`, `line_amount`, `received_quantity`, `remaining_quantity`. Đơn trả `subtotal_amount`, `created_by`, `approved_by`, `created_at`, `cancelled_at`, `cancellation_reason`.

Mỗi dòng phiếu nhập gửi `{purchase_order_item_id,received_quantity,actual_unit_price,lot_code?,manufacture_date?,expiry_date?}`. Response bổ sung `goods_receipt_item_id`, `purchase_unit_id`, `base_quantity`, `line_amount`. Backend lấy đơn vị/hệ số từ snapshot đơn mua; giao diện không gửi hay sửa số lượng cơ sở.

Tra cứu metadata dùng GET `/purchasing/suppliers`, `/purchasing/suppliers/:id`, `/purchasing/supplier-ingredients`, `/inventory/units`. Supplier picker tìm mã/tên có debounce 350 ms và phân trang máy chủ. Lookup liên kết/đơn vị có giới hạn rõ 1.000 bản ghi mỗi loại, không dùng làm aggregate. Khi thiếu metadata vẫn giữ ID thật, không tự đặt tên/đơn vị.

## State machine và quy tắc

- PO tạo DRAFT. DRAFT → PENDING_APPROVAL → APPROVED → ORDERED. Mỗi bước xác nhận riêng, kiểm tra capability và gán `actor_id` từ current user của session. Không còn ô nhập ID người thực hiện; backend Inventory Auth xác thực JWT và ghi đè actor theo current user.
- Chỉ DRAFT chưa có phiếu nhập được sửa. Supplier và số chứng từ không thuộc update schema. DRAFT/PENDING_APPROVAL/APPROVED/ORDERED được hủy với lý do khi chưa có phiếu CONFIRMED. Đơn đã nhận không được sửa/hủy.
- Phiếu nhập chỉ lập từ ORDERED/PARTIALLY_RECEIVED. Số nhập mặc định trống, 0/bỏ trống không gửi. Có thể tách một dòng đơn thành nhiều mã lô, tổng các lô kiểm tra theo remaining của dòng đơn.
- Tạo phiếu luôn DRAFT và chưa tăng tồn. Người dùng kiểm tra detail rồi chốt explicit bằng modal tóm tắt số lô, giá trị và lượng cơ sở từng lô (không cộng lẫn đơn vị).
- Confirm kiểm tra lại remaining, tạo một stock lot và movement RECEIPT/IN mỗi dòng, cập nhật PO PARTIALLY_RECEIVED/RECEIVED trong transaction. CONFIRMED không sửa/hủy. DRAFT không giữ chỗ lượng hàng; draft sai phải hủy và tạo lại vì chưa có PATCH phiếu nhập.
- Ngày nhập từ ngày đặt đến hôm nay; sản xuất không sau ngày nhập; hết hạn không trước ngày nhập/sản xuất. Hạn dùng date-only không qua timezone. Phiếu hồi tố với lô đã hết hạn hiện tại có cảnh báo, backend sẽ tạo lô EXPIRED.
- Các giá thỏa thuận/thực nhận cần người dùng nhập; không tự điền `latest_unit_price`. Giá tham khảo chỉ có nhãn thông tin. Tiền/số lượng giữ chuỗi decimal; hỗ trợ dấu phẩy Việt Nam. Số lượng tối đa 3 chữ số sau dấu thập phân, giá 2 chữ số sau dấu thập phân, giới hạn NUMERIC(14,s). Kiểm tra lượng mua tối thiểu và lượng quy đổi chính xác 0,001. Mỗi dòng tiền làm tròn HALF_UP 2 chữ số rồi cộng, dùng decimal.js.

## Lỗi, cập nhật dữ liệu và an toàn form

- 400/422: validation nội tuyến về giá, số lượng và ngày; actor lấy từ session và không chỉnh trong form. Lỗi phía server hiển thị error panel; 401 xóa session và về login, 403 hiển thị trang không đủ quyền Kho nếu vẫn ở route phát sinh request; 404/5xx theo lớp lỗi chung.
- 409: giữ payload; hướng dẫn đối chiếu trạng thái, số còn lại hoặc mã lô. Receipt editor có nút tải lại remaining, giữ các dòng đã nhập khi refresh. Khi PO chuyển sang không nhận được, chặn lưu và giữ dữ liệu để đối chiếu.
- Chống submit lặp bằng khóa ref trong `useMutation`; disable nút; không optimistic update hoặc tự retry mutation.
- Mọi mutation thành công phát sự kiện refresh của feature inventory: các query đang mở tải lại; route mới luôn đọc dữ liệu mới. Tạo PO/receipt chuyển tới mã chứng từ đã lưu. Guard bảo vệ rời trang/reload khi form dirty.
- Trang phiếu đã chốt dẫn tới danh sách lô theo ingredient và movement RECEIPT theo ingredient, hiển thị mã lô để đối chiếu. API receipt chưa trả stock_lot_id và stock-lots chưa lọc nguồn receipt nên không giả vờ có liên kết trực tiếp tới lô vừa tạo.

## Khoảng trống backend và giới hạn hiển thị

- PO chưa lọc mã, khoảng ngày tạo/ngày dự kiến; không cung cấp lịch sử transition/timestamp duyệt/đặt. UI chỉ hiện sự kiện có thật và trạng thái hiện tại.
- GR list chưa hỗ trợ tìm mã chứng từ, supplier, mã đơn chuỗi; chỉ có ID đơn mua. PO list chưa có supplier name, GR list chưa có PO number/supplier. UI fallback ID thật và liên kết chi tiết khi lookup không có.
- Lookup editor có giới hạn 1.000 mappings/units để ngăn tải vô hạn; cần endpoint tìm mapping theo tên nguyên liệu có pagination, hoặc expand snapshot label trong PO/GR cho danh mục lớn hơn.
- Không có API sửa receipt draft, xóa chứng từ, sửa phiếu đã chốt, trả hàng, công nợ hoặc phê duyệt nhiều cấp. Không tạo nút nghiệp vụ giả.
- Inventory Auth riêng bảo vệ các router mua/nhập bằng JWT và permission DB. Backend ghi đè created_by/received_by/actor_id từ current user, không tin body. Confirm receipt ghi movement.performed_by bằng user xác nhận. Xem [contract](inventory-auth-integration.md).

## Kiểm thử

- `src/features/inventory/pages/PurchasingPages.test.tsx`: state machine, HALF_UP, giới hạn số, MOQ, split-lot remaining chính xác, ngày, loading/empty/error, validation, 409 giữ dữ liệu, refresh remaining, unsaved guard, chống double submit, luồng tạo PO → ba bước duyệt → hai receipt draft và confirm explicit bằng API mock theo contract. Session test xác minh attribution đúng user, nhân viên kho không duyệt đơn và người chỉ có `PURCHASE_MANAGE` không chốt/hủy phiếu nhập.
- `e2e/purchasing-flow.spec.ts`: đăng nhập thật qua Inventory Auth, tạo PO/chuyển trạng thái/nhận hai lần và đối chiếu stock delta/remaining, lô nguồn, responsive 390px. Frontend 5174 dùng production adapter, API Auth/nghiệp vụ thật trên SQLite 8011 có marker auth=inventory-real-backend. Không mock login/me; không ghi Neon.
- Lệnh: `npm run test -- src/features/inventory/pages/PurchasingPages.test.tsx`; `npx playwright test e2e/purchasing-flow.spec.ts`. Trạng thái kết quả cuối theo tài liệu bàn giao/chạy thực tế, không coi test mock là kiểm thử PostgreSQL/Neon.
