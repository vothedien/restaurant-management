# Mua hàng, nhập kho, tồn kho, kiểm kê và tiêu hao món

Tài liệu bàn giao backend Người 2. API A–D dùng các bảng hiện có; E cung cấp service kho độc lập để tích hợp khi Người 1 bổ sung luồng hoàn thành món. Không tạo lại 33 bảng, không thêm luồng order/thanh toán/RBAC và không triển khai AI.

Các JSON dưới đây chỉ dành cho môi trường demo/test độc lập. **Không chạy các yêu cầu ghi này trên Neon của người dùng.** Trong đợt triển khai này không chạy migration, seed `--apply` hoặc ghi dữ liệu Neon. Test dùng SQLite trong bộ nhớ, thay dependency `get_db`; cấu hình test tắt đọc file `.env` trước khi import ứng dụng.

## Schema đã đối chiếu

Nguồn chuẩn: [DDL](../../database/restaurant_ai_database.sql), [model inventory](../app/db/models/inventory.py), [model catalog](../app/db/models/catalog.py), [model sales](../app/db/models/sales.py).

| Bảng | Cột/ràng buộc đang dùng |
| --- | --- |
| `supplier_ingredients` | Liên kết nhà cung cấp–nguyên liệu duy nhất; `purchase_unit_id`, `base_qty_per_purchase_unit > 0`, `minimum_order_qty > 0`, `is_active`. Hai FK nhà cung cấp/nguyên liệu không đổi qua API cập nhật mapping. |
| `purchase_orders` | Số đơn duy nhất, supplier FK, `created_by` bắt buộc, `approved_by` nullable, ngày đặt/ngày dự kiến, subtotal, trạng thái, thông tin hủy. `proposal_id` tồn tại nhưng không dùng cho luồng thủ công này. |
| `purchase_order_items` | Unique `(purchase_order_id, supplier_ingredient_id)`; số lượng dương; lưu đơn vị mua, hệ số quy đổi và giá thỏa thuận tại thời điểm lập đơn. `ordered_base_qty` và `line_amount` là cột generated, không gán trực tiếp. |
| `goods_receipts` | Số phiếu duy nhất, PO FK, `receipt_date`, chứng từ nhà cung cấp, `received_by`, trạng thái. Không có `confirmed_at`. |
| `goods_receipt_items` | PO-item FK, số lượng mua, đơn vị, số lượng cơ sở, giá nhập, mã lô, ngày sản xuất/hạn dùng. `line_amount` generated. Một PO-item có thể xuất hiện trong nhiều phiếu và nhiều dòng lô. |
| `stock_lots` | Unique `(ingredient_id, lot_code)` và unique `goods_receipt_item_id` nullable; giá cơ sở `unit_cost`, ngày sản xuất/hạn dùng, số lượng nhận/còn. Check hiện có: `received_quantity > 0` và `0 <= current_quantity <= received_quantity`. |
| `stock_movements` | Số lượng luôn dương, `direction = IN/OUT`, loại `RECEIPT/CONSUMPTION/ADJUSTMENT/RETURN`; FK nguồn tùy loại tới order item, receipt item hoặc stocktake item. Không có bảng số dư riêng; số dư tính từ lô. |
| `stocktakes`, `stocktake_items` | Snapshot số hệ thống, số thực đếm không nullable, chênh lệch generated, lý do điều chỉnh; unique `(stocktake_id, stock_lot_id)`. Không có cột `counted` hoặc revision của snapshot. |
| `order_items`, `recipe_items` | Order item có số món nguyên dương, `COMPLETED`, `completed_at`, recipe-version FK nullable. Recipe item lưu `base_quantity` đã quy đổi; E dùng snapshot này. |

Các nguồn phát sinh trong `stock_movements` dùng FK nullable, một số FK có `ON DELETE SET NULL` theo DDL. API mới không xóa lịch sử đã chốt. Những writer trực tiếp ngoài các service này vẫn phải tuân thủ cùng quy tắc transaction/khóa.

DDL không khai báo unique cho `stock_movements.movement_number`; ORM trước đây lại có `unique=True`. Đã bỏ khai báo sai ở ORM để khớp DDL. Đây là sửa mapping, **không cần migration**; chống chốt lặp dựa vào khóa nguồn và trạng thái/biến động đã lưu, không dựa vào mã movement.

## Quy ước chung

- Prefix: `/api/v1`. Response: `{"success": true, "message": "...", "data": ...}`; lỗi nghiệp vụ dùng `success: false`.
- Danh sách mới có `items`, `total`, `limit`, `offset`; mặc định 20 dòng, tối đa 100 dòng/trang.
- `400`: dữ liệu hợp lệ về cấu trúc nhưng sai nghiệp vụ; `404`: không có đối tượng; `409`: sai trạng thái, thiếu tồn, xung đột/chốt trên snapshot cũ; `422`: sai payload; `503`: lỗi lưu trữ được che thông tin driver.
- Số lượng/giá nên gửi bằng chuỗi JSON để giữ Decimal. Số lượng cơ sở có tối đa 3 chữ số thập phân (`NUMERIC(14,3)`); giá mua 2 số (`14,2`), giá cơ sở lô 4 số (`14,4`). Giá do người lập cung cấp, không tự lấy giá demo hoặc `latest_unit_price`.
- Mua/nhập kho và xuất thủ công từ chối phép quy đổi không biểu diễn chính xác tới `0.001`, cũng như tràn precision. Tiền/giá cơ sở dùng `ROUND_HALF_UP`. Công thức đã có quy tắc riêng: làm tròn định lượng cơ sở tới `0.001` khi lưu recipe item; E giữ nguyên snapshot đó.
- Mapping nhà cung cấp có thể mô tả đơn vị đóng gói bằng hệ số riêng, ví dụ BOX → gram; không tự suy ra hệ số từ tên đơn vị. Xuất thủ công dùng đúng đơn vị cơ sở hoặc conversion trực tiếp cùng dimension, không tự đảo conversion hoặc dò chuỗi chuyển đổi.
- Ứng dụng hiện chưa có dependency xác thực/phân quyền cho các route này. `created_by`, `actor_id`, `received_by`, `performed_by`, `completed_by` kiểm tra user tồn tại và ACTIVE; **đó là kiểm tra FK/nghiệp vụ, không phải phân quyền**. Không viết lại RBAC của Người 1.

`Ingredient.base_unit_id` không được đổi khi đã có recipe item, supplier mapping, lô hoặc lịch sử kho tham chiếu. Cập nhật nguyên liệu và chuẩn bị recipe item cùng khóa nguyên liệu theo ID tăng dần, tránh race đổi đơn vị cơ sở trong lúc lưu định lượng. `Unit.dimension` bất biến sau khi tạo; cần dimension khác thì tạo đơn vị mới.

## Tệp triển khai

Các đường dẫn dưới đây tương đối với `backend/`; mỗi nhóm mới giữ các lớp router, service, repository và schemas riêng:

| Phạm vi | Tệp mới hoặc cập nhật |
| --- | --- |
| Đơn mua | `app/modules/purchasing/order_schemas.py`, `order_repository.py`, `order_service.py`, `order_router.py` |
| Phiếu nhập | `app/modules/purchasing/receipt_schemas.py`, `receipt_repository.py`, `receipt_service.py`, `receipt_router.py` |
| Kho | `app/modules/inventory/stock_common.py`, `stock_schemas.py`, `stock_repository.py`, `stock_service.py`, `stock_router.py` |
| Kiểm kê | `app/modules/inventory/stocktake_schemas.py`, `stocktake_repository.py`, `stocktake_service.py`, `stocktake_router.py` |
| Tiêu hao | `app/modules/inventory/consumption_schemas.py`, `consumption_repository.py`, `consumption_service.py` |
| Đăng ký API | `app/modules/purchasing/router.py`, `app/modules/inventory/router.py` |
| Bảo vệ lịch sử đơn vị | `app/modules/inventory/service.py`, `app/modules/inventory/repository.py`, `app/modules/recipes/repository.py` |
| Mapping DDL | `app/db/models/inventory.py`: bỏ unique không có trong DDL của movement number |
| Test | `tests/conftest.py`, `stock_fixtures.py`, `test_purchase_orders.py`, `test_goods_receipts.py`, `test_stock.py`, `test_stocktakes.py`, `test_consumption.py`, `test_workflow_demo.py` |
| Tài liệu | `README.md`, `docs/inventory-workflows.md` |

Không thay đổi frontend, module Sales/auth/catalog, DDL gốc hay Alembic. Các sửa đổi vẫn chưa commit trên nhánh `feature/purchasing-stock-workflows` để người dùng xem diff.

## A. Đơn mua hàng

Prefix đầy đủ: `/api/v1/purchasing/purchase-orders`.

| Method | Đường dẫn sau prefix | Chức năng/payload |
| --- | --- | --- |
| POST | rỗng | Tạo DRAFT: supplier, created_by và 1–200 dòng; mỗi dòng có `supplier_ingredient_id`, `ordered_quantity`, `expected_unit_price`. |
| GET | rỗng | Lọc `supplier_id`, `status`, phân trang. |
| GET | `/{order_id}` | Chi tiết kèm tổng đã nhận và còn phải nhận từng dòng. |
| PATCH | `/{order_id}` | Đổi ngày/ghi chú hoặc thay toàn bộ `items` khi DRAFT và chưa có phiếu nhập. |
| POST | `/{order_id}/status` | `status`, `actor_id`; hủy cần `cancellation_reason` không rỗng. |

Luồng trạng thái thủ công: `DRAFT → PENDING_APPROVAL → APPROVED → ORDERED`. Nhập hàng cập nhật `ORDERED → PARTIALLY_RECEIVED → RECEIVED`; không đặt trực tiếp hai trạng thái nhận hàng qua API chuyển trạng thái. DRAFT/PENDING_APPROVAL/APPROVED/ORDERED có thể hủy nếu chưa có phiếu nhập CONFIRMED. Không sửa hoặc hủy đơn đã nhận hàng. Gọi lại cùng trạng thái trả trạng thái đã lưu.

Mỗi mapping phải thuộc đúng supplier, đang hoạt động; supplier/nguyên liệu/đơn vị cần hợp lệ và hoạt động; số đặt phải đạt mức tối thiểu của mapping. Đơn vị/hệ số/giá trên dòng đơn là snapshot: sửa catalog supplier sau đó không đổi đơn đã lưu. Tạo, duyệt hoặc gửi đơn không tăng tồn.

## B. Phiếu nhập hàng

Prefix: `/api/v1/purchasing/goods-receipts`.

| Method | Đường dẫn sau prefix | Chức năng/payload |
| --- | --- | --- |
| POST | rỗng | Tạo DRAFT từ PO ORDERED/PARTIALLY_RECEIVED; `purchase_order_id`, `received_by`, 1–200 dòng. |
| GET | rỗng | Lọc `purchase_order_id`, `status`, `date_from`, `date_to`, phân trang. |
| GET | `/{receipt_id}` | Chi tiết phiếu và các dòng lô. |
| POST | `/{receipt_id}/confirm` | Chốt, không cần body. |
| POST | `/{receipt_id}/cancel` | Hủy DRAFT, không cần body; không hủy phiếu CONFIRMED. |

Mỗi dòng gửi `purchase_order_item_id`, `received_quantity`, `actual_unit_price`; có thể gửi `lot_code`, `manufacture_date`, `expiry_date`. Không nhận đơn vị/hệ số/số lượng cơ sở do client tự gán: lấy snapshot từ PO. Mã lô có thể bỏ trống để service tạo mã nội bộ.

Chỉ tính tổng đã nhận từ phiếu CONFIRMED. Nhiều phiếu DRAFT không giữ chỗ số lượng; service kiểm tra lại khi chốt, chặn tổng nhận vượt số đặt. Ngày nhận phải từ ngày đặt đến hôm nay; ngày sản xuất không sau ngày nhận, hàng không được hết hạn tại ngày nhận. Nếu chốt muộn sau hạn dùng, lô được lưu EXPIRED và không cấp xuất. Phiếu nháp sai được hủy rồi tạo lại; không có API sửa phiếu nhập đã lập.

Chốt phiếu tạo mỗi dòng một lô và movement RECEIPT/IN, đồng thời cập nhật PO trong cùng transaction. Không gộp mã lô trùng của cùng nguyên liệu: schema chỉ cho một receipt-item nguồn của một lô. Dùng mã lô nội bộ khác cho lần giao khác; trùng mã trả 409. Phiếu DRAFT không thay đổi tồn; chốt CONFIRMED lần nữa trả kết quả cũ, không nhập lần hai.

## C. Lô, số dư và biến động

Các đường dẫn dưới prefix `/api/v1/inventory`:

| Method | Đường dẫn | Chức năng/lọc |
| --- | --- | --- |
| GET | `/stock` | Tổng tồn theo nguyên liệu; `ingredient_id`, phân trang. |
| GET | `/stock-lots` | Lô; `ingredient_id`, `status`, `available_only`, phân trang. |
| GET | `/stock-lots/{lot_id}` | Chi tiết lô. |
| GET | `/stock-movements` | `ingredient_id`, `stock_lot_id`, `movement_type`, `occurred_from`, `occurred_to`, phân trang. Timestamp lọc phải có timezone. |
| POST | `/stock/issues` | Xuất thủ công: `ingredient_id`, `quantity`, `unit_id`, `performed_by`, `reason`. |
| POST | `/stock-lots/{lot_id}/adjust` | Đặt số thực tế theo đơn vị cơ sở: `actual_quantity`, `performed_by`, `reason`. |

`current_quantity` là tổng số còn của mọi lô nguyên liệu, kể cả lô bị chặn/hết hạn. `available_quantity` chỉ tính nguyên liệu ACTIVE và lô đủ điều kiện cấp xuất; `unavailable_quantity = current_quantity - available_quantity`. Nguyên liệu INACTIVE vẫn hiển thị tổng tồn nhưng tồn khả dụng bằng 0. Đối chiếu tổng `current_quantity` của danh sách lô với số tổng này, không cộng số lượng movement thiếu dấu direction.

Lô cấp xuất phải ACTIVE, còn số lượng, ngày sản xuất không ở tương lai và hạn dùng chưa qua. Cấp lô có hạn gần nhất trước (FEFO); không có hạn dùng xếp sau; hòa thì theo thời điểm tạo và ID. Xuất kho yêu cầu nguyên liệu ACTIVE. Mọi nguyên liệu đều được theo dõi qua lô trong luồng này, kể cả khi `manages_lot=false`, để giữ nguồn nhập và đối chiếu số dư.

Xuất thủ công ghi `ADJUSTMENT/OUT` cùng lý do, tiêu hao món ghi `CONSUMPTION/OUT`. Điều chỉnh đặt số thực tế: tăng ghi `ADJUSTMENT/IN`, giảm ghi `ADJUSTMENT/OUT`, không đổi thì không tạo movement. Không âm kho; service lập đủ kế hoạch phân bổ tất cả nguyên liệu rồi mới sửa lô. Thiếu bất kỳ nguyên liệu nào làm rollback toàn bộ nghiệp vụ.

Điều chỉnh tăng số còn **được hỗ trợ tới số lượng nhận ban đầu của lô**. Vượt `received_quantity` trả 409 vì check DDL hiện tại, không âm thầm sửa số lượng nhập gốc. Điều chỉnh/kiểm kê không tự mở khóa lô BLOCKED/EXPIRED.

Ví dụ xuất thủ công 0.100 KG nguyên liệu 1 (môi trường demo độc lập):

```json
{"ingredient_id": 1, "quantity": "0.100", "unit_id": 2, "performed_by": 1, "reason": "Hao hụt chế biến demo"}
```

## D. Kiểm kê

Prefix: `/api/v1/inventory/stocktakes`.

| Method | Đường dẫn sau prefix | Chức năng/payload |
| --- | --- | --- |
| POST | rỗng | Tạo DRAFT: `created_by`, tùy chọn `stocktake_number`, `notes`. |
| GET | rỗng | Lọc `status`, phân trang. |
| GET | `/{stocktake_id}` | Chi tiết snapshot/chênh lệch và `counted`. |
| POST | `/{stocktake_id}/start` | `stock_lot_ids`: 1–1000 ID không trùng. Chụp tồn và chuyển IN_PROGRESS. |
| PATCH | `/{stocktake_id}/items/{item_id}` | `actual_quantity`, `adjustment_reason` bắt buộc. |
| POST | `/{stocktake_id}/complete` | `completed_by`; chốt IN_PROGRESS → COMPLETED. |
| POST | `/{stocktake_id}/cancel` | Hủy DRAFT/IN_PROGRESS; không hủy COMPLETED. |

Phiếu chỉ kiểm kê những lô đã chọn, không tự bao gồm lô mới sinh sau đó. Bắt đầu phiếu lưu `system_quantity = actual_quantity = tồn lúc bắt đầu` nhưng chưa coi là đã đếm. DDL không có cột đánh dấu đã đếm; service dùng `adjustment_reason = NULL` cho chưa đếm, và bắt buộc ghi chú không rỗng khi xác nhận số đếm, kể cả khi khớp tồn. `counted` là trường response tính từ ghi chú, không phải cột mới.

Ghi số đếm không sửa tồn. Chốt yêu cầu mọi dòng đã đếm và snapshot còn đúng; chỉ các dòng chênh lệch tạo movement. Số đếm không âm, tối đa bằng `received_quantity` của lô; chênh lệch dương trong giới hạn đó được ghi nhận bình thường. Gọi complete lần nữa giữ nguyên actor/thời gian/kết quả, không điều chỉnh lần hai.

Quy tắc khi kho biến động trong lúc kiểm kê: so sánh tồn hiện tại với snapshot **và** tìm movement của các lô từ `started_at`. Nếu có xuất rồi nhập bù về cùng số lượng vẫn xem snapshot hết hiệu lực. Count/complete trả 409; hủy phiếu và lập phiếu mới. Không giữ khóa DB trong suốt thời gian nhân viên đếm; khóa chỉ tồn tại trong mỗi transaction API.

## E. Tiêu hao khi món hoàn thành

Chưa có endpoint order/kitchen hoàn thành món trong Sales; [SalesService](../app/modules/sales/service.py) hiện chỉ liệt kê bàn. Vì vậy chưa thể demo bước này qua một endpoint Sales thật. Không tự dùng thanh toán làm mốc, không thêm endpoint hoàn thành món giả.

[ConsumptionService](../app/modules/inventory/consumption_service.py) cung cấp:

- `consume_completed_item(session, order_item_id, performed_by=None)`: wrapper commit/rollback cho order item đã hoàn thành.
- `consume_in_transaction(session, order_item_id, performed_by=None)`: flush, không commit; dùng trong transaction hoàn thành món do Người 1 quản lý.

Order item phải được lưu với `status=COMPLETED`, có `completed_at` và gắn `recipe_version_id` đúng dish. Thiếu pin công thức trả BusinessRuleError/400; không tự lấy công thức ACTIVE hôm nay. Recipe DRAFT/rỗng không hợp lệ; phiên bản đã gắn nay INACTIVE/EXPIRED vẫn dùng được. Nhu cầu = `recipe_items.base_quantity × order_items.quantity`; sửa conversion hoặc kích hoạt công thức mới không đổi nhu cầu của đơn đã gắn phiên bản cũ.

Khóa order item trước khi kiểm tra movement CONSUMPTION đã có. Có movement thì trả kết quả cũ với `already_consumed=true`; không trừ lần hai dù tồn hiện tại đã ít hơn nhu cầu ban đầu. Khi xử lý mới, thiếu một nguyên liệu hoặc lỗi ghi DB làm rollback tất cả lô/movement cùng thay đổi completion trong transaction của caller.

Điểm gọi dành cho service Sales tương lai, **không phải endpoint mới hay script chạy trên Neon**:

```python
from app.modules.inventory.consumption_service import ConsumptionService

# Nằm trong transaction của service hoàn thành món do Người 1 triển khai.
# Caller đã khóa OrderItem, kiểm tra transition/quyền và gắn recipe_version_id.
with session.begin():
    order_item.status = "COMPLETED"
    order_item.completed_at = completion_time
    ConsumptionService().consume_in_transaction(
        session, order_item.order_item_id, performed_by=actor_id
    )
# Chỉ commit sau khi cả trạng thái món và tiêu hao đều thành công.
```

Nếu caller đã có transaction do query trước đó, gọi `consume_in_transaction` ngay trong transaction đang quản lý; không lồng thêm `session.begin()` hoặc gọi wrapper tự commit. Người 1 vẫn chịu trách nhiệm xác nhận transition món hoàn thành và không sửa số món/recipe pin của món đã tiêu hao.

## Demo đầy đủ trên môi trường độc lập

Dùng [test_workflow_demo.py](../tests/test_workflow_demo.py) cho chuỗi chạy offline. Các JSON sau mô tả cùng loại nghiệp vụ; các ID số chỉ minh họa, phải lấy ID thực từ response. Điều kiện demo: user/supplier ACTIVE ID 1; đơn vị G=1, KG=2; nguyên liệu FLOUR=1, CHEESE=2 dùng gram; mappings 1/2 có hệ số 1000 gram/KG và mức đặt tối thiểu 1 KG. Không tạo dữ liệu thật từ các giả định ID này.

1. `POST /api/v1/purchasing/purchase-orders`:

```json
{
  "supplier_id": 1,
  "created_by": 1,
  "items": [
    {"supplier_ingredient_id": 1, "ordered_quantity": "2.000", "expected_unit_price": "35000.25"},
    {"supplier_ingredient_id": 2, "ordered_quantity": "1.000", "expected_unit_price": "100000.00"}
  ]
}
```

2. Gọi `POST /api/v1/purchasing/purchase-orders/{order_id}/status` lần lượt với ba body:

```json
{"status": "PENDING_APPROVAL", "actor_id": 1}
```

```json
{"status": "APPROVED", "actor_id": 1}
```

```json
{"status": "ORDERED", "actor_id": 1}
```

Tồn vẫn bằng 0 nếu môi trường demo ban đầu chưa có lô.

3. `POST /api/v1/purchasing/goods-receipts`, giả sử PO=1, dòng flour=1 và cheese=2:

```json
{
  "purchase_order_id": 1,
  "received_by": 1,
  "items": [
    {"purchase_order_item_id": 1, "received_quantity": "1.000", "actual_unit_price": "35000.25", "lot_code": "DEMO-FLOUR-01"},
    {"purchase_order_item_id": 2, "received_quantity": "1.000", "actual_unit_price": "100000.00", "lot_code": "DEMO-CHEESE-01"}
  ]
}
```

Phiếu DRAFT chưa tăng tồn. `POST /api/v1/purchasing/goods-receipts/{receipt_id}/confirm` làm tồn thành 1000g flour/1000g cheese, PO PARTIALLY_RECEIVED. Gọi confirm lại không đổi tồn. Lập/chốt phiếu thứ hai cho dòng flour với `received_quantity="1.000"` và `lot_code="DEMO-FLOUR-02"`: tồn thành 2000g/1000g, PO RECEIVED.

4. Đọc `GET /api/v1/inventory/stock`, `/stock-lots`, `/stock-movements?movement_type=RECEIPT`. Dùng test offline tạo order item đúng schema, gắn công thức 250g flour + 2g cheese/món, số món=2 rồi gọi service E sau completion. Tồn giảm 500g flour và 4g cheese, còn 1500g/996g. Đây là kiểm chứng service; endpoint Sales cho thao tác này vẫn đang chờ Người 1.

5. `POST /api/v1/inventory/stocktakes`:

```json
{"created_by": 1, "notes": "Kiểm kê sau ca demo"}
```

`POST /api/v1/inventory/stocktakes/{stocktake_id}/start`, giả sử lô flour đầu=1, cheese=2:

```json
{"stock_lot_ids": [1, 2]}
```

Lấy `stocktake_item_id` từng dòng từ response. Nếu lô flour đầu còn 500g, ghi 490g bằng PATCH `/api/v1/inventory/stocktakes/{stocktake_id}/items/{flour_item_id}`:

```json
{"actual_quantity": "490.000", "adjustment_reason": "Thiếu 10g khi cân cuối ca"}
```

Ghi dòng cheese dù khớp số hệ thống:

```json
{"actual_quantity": "996.000", "adjustment_reason": "Đã cân, khớp tồn hệ thống"}
```

`POST /api/v1/inventory/stocktakes/{stocktake_id}/complete`:

```json
{"completed_by": 1}
```

Tồn flour tổng còn 1490g, cheese 996g; một movement ADJUSTMENT/OUT 10g gắn stocktake item. Lô flour thứ hai không chọn kiểm kê giữ nguyên. Gọi complete lại không tạo movement mới. Nếu có writer sửa kho sau start, nhận 409 và lập phiếu mới thay vì áp số đếm lên snapshot cũ.

## Transaction và kiểm chứng đồng thời

Service là ranh giới commit/rollback; repository không tự commit. Response được chuyển thành schema trước commit để tránh truy vấn lazy sau khi đã ghi thành công.

- Nhập hàng khóa PO trước phiếu nhập; các phiếu khác nhau cùng PO phải đợi nhau trước khi cộng tổng đã nhận. Tạo/chuyển trạng thái PO và chốt/hủy phiếu nhập cùng tuân theo khóa PO này.
- Supplier/mapping theo thứ tự supplier → nguyên liệu tăng dần → mapping tăng dần. Writer kho khóa nguyên liệu trước lô; các lô được khóa theo ID tăng dần rồi mới phân bổ theo FEFO.
- Chốt kiểm kê khóa stocktake → nguyên liệu → lô; tiêu hao khóa order item → nguyên liệu → lô. Khóa nguyên liệu bảo vệ cả tình huống hiện chưa có lô để khóa.
- Các lần đọc sau khi đợi khóa dùng `populate_existing=True`, tránh dùng trạng thái cũ trong identity map. Khóa giữ đến cuối transaction.
- Mốc movement/kiểm kê dùng PostgreSQL `clock_timestamp()` sau khi lấy khóa, không dùng thời điểm bắt đầu transaction để bỏ sót writer phải chờ khóa. Ngoài PostgreSQL, test dùng thời gian UTC.

Test SQLite kiểm chứng transaction/rollback, FK, generated columns, quy tắc nghiệp vụ và câu SQL khóa biên dịch theo dialect PostgreSQL. **SQLite bỏ qua `FOR UPDATE`: test này không chứng minh xử lý đồng thời thật trên PostgreSQL.** Không có PostgreSQL test riêng được cung cấp trong phiên làm việc; chưa chạy test cạnh tranh giao dịch trên PostgreSQL, không dùng Neon để thay thế. Sau khi có DB test riêng, cần chạy hai session đồng thời: cùng confirm một phiếu, hai phiếu vượt phần PO còn lại, hai món cạnh tranh cùng lô và complete kiểm kê cạnh tranh writer kho.

SQLite cũng không mô phỏng hoàn toàn `NUMERIC` của PostgreSQL: phép tính generated có thể đi qua số thực nhị phân ở điểm làm tròn nửa đơn vị. Service dùng Decimal và làm tròn tiền rõ ràng; việc đối chiếu generated `line_amount` tại các điểm này cần PostgreSQL test riêng. Không thay cột generated bằng dữ liệu tính giả để làm test SQLite giống PostgreSQL.

## Chạy test và Ruff

Chạy từ thư mục gốc repository với Python 3.11+ và dependencies đã cài trong virtualenv:

```powershell
& '.\backend\.venv\Scripts\python.exe' -m pytest -q backend/tests
& '.\backend\.venv\Scripts\ruff.exe' check backend
& '.\backend\.venv\Scripts\ruff.exe' format --check backend
```

Virtualenv Python trên máy bàn giao từng trỏ tới bản Python đã bị gỡ. Runtime cục bộ tạm đã chuẩn bị cho phiên này có thể thay executable, không cần sửa URL hay cấu hình DB:

```powershell
& '.\tmp\runtime\python311\python.exe' -m pytest -q backend/tests
& '.\backend\.venv\Scripts\ruff.exe' check backend
& '.\backend\.venv\Scripts\ruff.exe' format --check backend
```

`tmp/runtime` là công cụ cục bộ tạm, không phải dependency được commit; máy khác dùng virtualenv Python 3.11+ thông thường. Bộ test nghiệp vụ dùng `tests/stock_fixtures.py`, schema SQLite clone trong bộ nhớ và user demo độc lập. Test không đọc `backend/.env`, không phụ thuộc Neon. Kết quả và tổng số test cuối cùng lấy từ log chạy thực tế, không cố định con số trong tài liệu này.

Các nhóm cần kiểm tra khi thay đổi: purchase orders (A), goods receipts (B), stock (C), stocktakes (D), consumption (E), workflow demo, cùng các test inventory/recipes/suppliers hiện có. Không chạy `seed --apply`, `alembic upgrade` hoặc ví dụ API ghi vào DB thật để xác minh.

## Đề xuất migration duy nhất cho số đếm vượt lượng nhận gốc

Chưa triển khai/áp dụng migration. Với schema hiện tại, điều chỉnh hoặc kiểm kê lô từ 50 lên 60 được phép nếu `received_quantity=100`; đếm 101 trả 409. Để hỗ trợ vượt lượng nhập gốc mà vẫn giữ lịch sử `received_quantity`, đề xuất Người 2 duyệt thay đúng check sau:

```sql
-- Phương án để duyệt, KHÔNG phải lệnh đã chạy.
ALTER TABLE restaurant_ai.stock_lots
    DROP CONSTRAINT ck_stock_lots_current_qty;

ALTER TABLE restaurant_ai.stock_lots
    ADD CONSTRAINT ck_stock_lots_current_qty
    CHECK (current_quantity >= 0);
```

Giữ nguyên `ck_stock_lots_received_qty` (`received_quantity > 0`), unique/FK và các cột hiện có. Sau khi được thống nhất, cần Alembic migration tương ứng, đổi check ORM và bỏ kiểm tra trần trong `StockService.validate_count`; mở rộng test điều chỉnh/kiểm kê dương. Không sửa `received_quantity` của lô nhập thật. Nếu muốn downgrade, phải xử lý các lô đang có `current_quantity > received_quantity` trước khi khôi phục check cũ.

Phần còn chờ: quyết định migration này cho tồn dư vượt trần; interface hoàn thành món thật của Người 1 để gọi E trong cùng transaction; môi trường PostgreSQL test riêng để kiểm chứng cạnh tranh giao dịch. Các chức năng A–D trong giới hạn schema và service E không cần đợi những phần này để chạy test offline.
