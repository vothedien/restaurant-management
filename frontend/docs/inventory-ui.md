# Giao diện module kho

## Kiến trúc

Module nằm trong `src/features/inventory`: `api/` giữ hợp đồng HTTP, `types/` giữ kiểu dữ liệu, `auth/` nối Inventory Auth riêng, `hooks/` quản lý query/mutation/unsaved state, `components/` và `pages/` giữ các workflow đã có. Dùng React, TypeScript, Router, Axios và CSS hiện hữu. Backend Inventory Auth dùng lại RBAC/audit tables; không sửa schema hoặc module Auth/Sales của Người 1.

`/inventory/*` có layout độc lập, không nằm trong `MainLayout` của Sales và không có liên kết Sales, bàn, order, bếp hoặc thanh toán. Logo về `/inventory`; thanh trên hiển thị tên người dùng, vai trò và đăng xuất. Menu desktop/mobile lọc theo quyền; menu mobile đóng/mở bằng nút. `main.tsx` sử dụng data router của React Router để chặn điều hướng khi chưa lưu; tích hợp routing dùng chung chỉ tách nhánh Kho. Route kho được lazy load theo nhóm. CSS được giới hạn trong `.inventory`, gồm bảng desktop, card nhận hàng và kiểm đếm mobile, dialog HTML native, focus ring và reduced motion.

## Đăng nhập và quyền

Mở `/inventory/login` để đăng nhập bằng username/password thật có quyền Kho. URL nghiệp vụ chuyển người chưa đăng nhập về login với returnTo nội bộ; người thiếu quyền nhận 403 trước mount dữ liệu. Backend riêng `/api/v1/inventory-auth` xác minh bcrypt và cấp JWT audience inventory. Khi secret chưa cấu hình, form báo cần quản trị cấu hình; không đăng nhập giả.

Provider/transport xử lý session, 401/403, logout và actor. Token lưu bằng sessionStorage với key inventory_access_token; login rồi /me lấy quyền mới nhất. Không refresh token tự động. Mapping permission frontend đồng bộ dependency server; REPORT_VIEW đơn lẻ không đủ vào Kho. Xem [Inventory Auth](inventory-auth-integration.md).

## Route

| Nhóm | Route |
| --- | --- |
| Đăng nhập công khai | `/inventory/login?returnTo=<đường dẫn Kho nội bộ>` |
| Tổng quan | `/inventory`, `/inventory/alerts` |
| Nguyên liệu | `/inventory/ingredients`, `/inventory/ingredients/:id` |
| Đơn vị | `/inventory/units` (đơn vị và quy đổi) |
| Công thức | `/inventory/recipes`, `/inventory/recipes/:dishId?version=<recipe_version_id>` |
| Nhà cung cấp | `/inventory/suppliers`, `/inventory/suppliers/:id` |
| Đơn mua | `/inventory/purchase-orders`, `/new`, `/:id`, `/:id/edit` dưới prefix này |
| Phiếu nhập | `/inventory/goods-receipts`, `/new?purchase_order_id=<id>`, `/:id` |
| Tồn | `/inventory/stock`, `/inventory/lots`, `/inventory/lots/:id`, `/inventory/movements` |
| Xuất/điều chỉnh | `/inventory/adjustments/new?ingredient_id=<id>` hoặc `?lot_id=<id>` |
| Kiểm kê | `/inventory/stocktakes`, `/inventory/stocktakes/new`, `/inventory/stocktakes/:id` |
| Báo cáo | `/inventory/reports` |

Refresh trực tiếp route dùng SPA fallback về index.html. Provider đọc token Kho và gọi /inventory-auth/me để kiểm tra user/status/quyền trước khi mount dữ liệu. Production host cần cấu hình SPA fallback.

## Hợp đồng API và trạng thái

Base URL lấy từ `VITE_API_URL` và timeout kế thừa cấu hình Axios hiện có. Kho dùng Axios instance riêng để 401/403/token không làm thay đổi hành vi Sales. Helpers `get/post/patch/put/del` thêm `/api/v1` và unwrap `{success,message,data}`. Transport chỉ gắn Bearer token do adapter session cung cấp; không ghi token ra log, UI hoặc URL. Tất cả danh sách trả `{items,total,limit,offset}`, giới hạn trang API tối đa 100. Không dùng dữ liệu mock trong runtime production.

Xem các bảng chi tiết trong `inventory-api-contract.md` và `inventory-purchasing-contract.md` (được tạo cùng đợt triển khai).

| Màn hình | Endpoint sau `/api/v1` | Request / query chính | Response / nghiệp vụ |
| --- | --- | --- | --- |
| Tồn | GET `/inventory/stock` | `ingredient_id, limit, offset` | balance gồm current, available, unavailable, đơn vị cơ sở |
| Lô | GET `/inventory/stock-lots`, `/{id}` | `ingredient_id,status,available_only,limit,offset` | lượng nhập, lượng còn, unit_cost, ngày sản xuất/hết hạn, dòng nhập nguồn |
| Sổ kho | GET `/inventory/stock-movements` | `ingredient_id,stock_lot_id,movement_type,occurred_from,occurred_to,limit,offset` | direction IN/OUT độc lập với loại; không sửa/xóa |
| Xuất | POST `/inventory/stock/issues` | ingredient_id, quantity decimal string, unit_id, performed_by, reason | movements; chọn lô FEFO trên server |
| Điều chỉnh | POST `/inventory/stock-lots/{id}/adjust` | actual_quantity decimal string, performed_by, reason | đặt số thực tế, không phải delta; tối đa lượng nhập gốc |
| Kiểm kê | GET/POST `/inventory/stocktakes`, GET `/{id}` | danh sách lọc status/limit/offset; tạo created_by, notes, mã tùy chọn | DRAFT → IN_PROGRESS → COMPLETED; DRAFT/IN_PROGRESS có thể CANCELLED |
| Bắt đầu kiểm kê | POST `/inventory/stocktakes/{id}/start` | stock_lot_ids từ 1–1000 ID duy nhất | snapshot tồn và các dòng `counted=false` |
| Ghi số đếm | PATCH `/inventory/stocktakes/{id}/items/{item_id}` | actual_quantity, adjustment_reason không rỗng | counted=true; chưa sửa tồn |
| Chốt kiểm kê | POST `/inventory/stocktakes/{id}/complete` | completed_by | mọi dòng đã kiểm, snapshot còn hợp lệ; tạo movement cho chênh lệch |
| Hủy kiểm kê | POST `/inventory/stocktakes/{id}/cancel` | không body | không áp số đếm vào tồn |

Đơn mua: DRAFT → PENDING_APPROVAL → APPROVED → ORDERED → PARTIALLY_RECEIVED → RECEIVED. Chỉ DRAFT được sửa; hủy yêu cầu lý do và chưa nhận hàng. Hai trạng thái nhận hàng do confirm phiếu nhập cập nhật.

Phiếu nhập: DRAFT → CONFIRMED hoặc CANCELLED. Không có PATCH phiếu nháp. Nhập từ ORDERED/PARTIALLY_RECEIVED, đối chiếu tổng các lô của cùng dòng đơn với remaining_quantity. Lập nháp chưa giữ chỗ và chưa tăng tồn. Confirm kiểm tra lại số còn lại, tạo lô/movement cùng transaction. Không tự retry mutation.

Lô: ACTIVE, DEPLETED, EXPIRED, BLOCKED. Tồn khả dụng lấy từ server; không dùng tổng tồn để cho phép xuất. FEFO chỉ được xem trước nếu đã tải đủ tập lô cấp xuất (có giới hạn). Lô không hạn xếp cuối, rồi created_at và ID để phân xử.

## An toàn dữ liệu và lỗi

- Mutation khóa bằng ref ngay lúc gọi và disable nút; chỉ cập nhật sau response thành công. Phát sự kiện refresh trong module; chỉ query đang mount trong kho được tải lại, route mới luôn fetch mới.
- Query có AbortController, bỏ phản hồi cũ theo key; search danh mục debounce 350 ms. Khi refresh thất bại giữ dữ liệu đã tải để không làm mất form đang sửa.
- Cảnh báo trước khi rời pathname hoặc query string có thay đổi chưa lưu và trước khi reload/đóng tab. Dialog dùng native focus containment, Escape và khôi phục focus.
- 400/422 hiển thị lỗi dữ liệu; frontend validation theo field. Backend hiện bỏ chi tiết Pydantic 422 nên không thể map mọi lỗi server tới field.
- 401 xóa session/token client và về login; 403 hiển thị trang không có quyền trong Kho nếu người dùng vẫn ở route phát sinh request. Response 403 muộn từ route trước không chặn trang mới; lỗi của session cũ không làm hết phiên mới. 404 thiếu đối tượng, 409 hướng dẫn đối chiếu. Không tự áp số đếm lên snapshot mới. Giữ số đếm chưa lưu sau conflict; mở biến động, tải lại để đối chiếu, hủy và lập phiếu mới.
- 500/503/network có retry query; không retry nghiệp vụ tự động. Hiển thị request ID nếu server trả header; không in stack trace/response thô.
- Không còn ô nhập actor ID. Frontend hiển thị tên session và gửi actor legacy để tương thích; router server luôn ghi đè created_by, received_by, performed_by, completed_by, actor_id bằng authenticated user. Recipe creator và movement khi confirm receipt cũng do server gán. API thiếu token trả 401, thiếu quyền trả 403.

## Decimal, tiền, ngày

`decimal.js` giữ số form/API dạng string; quantity scale 3, giá scale 2, quy đổi scale 6 theo schema. Không dùng cộng/trừ/nhân float cho tiền/tồn. Tiền PO làm tròn HALF_UP theo từng dòng như backend. Nhận dấu phẩy hoặc dấu chấm thập phân; không chấp nhận chuỗi trộn dấu phân cách hàng nghìn.

Hiển thị tiếng Việt; VND với tối đa 2 chữ số thập phân theo dữ liệu. Timestamp hiển thị `Asia/Ho_Chi_Minh`, timestamp UTC không offset từ test được hiểu là UTC. Date-only giữ ISO trên API và hiển thị DD/MM/YYYY, không đổi timezone; ô chọn ngày native theo locale của trình duyệt. Ngưỡng hạn dùng tập trung 3/7/14 ngày. Hết hạn khi ngày hết hạn nhỏ hơn hôm nay; hàng hết hạn hôm nay vẫn còn trong ngày sử dụng theo backend.

## Chỉ số, cảnh báo và báo cáo

Tổng quan và cảnh báo chỉ gọi nhóm dữ liệu người dùng có quyền xem. Trong mỗi nhóm được phép, tổng quan đọc đầy đủ nguyên liệu, tồn, lô trong giới hạn 1.000 bản ghi mỗi tập; dùng total của query lọc để đếm chứng từ chờ. Không cộng số lượng khác nguyên liệu/đơn vị. Tồn thấp/hết hàng dựa trên available_quantity và nguyên liệu ACTIVE. Cảnh báo hạn chỉ tính lô còn lượng, kể cả bị khóa; expired status được tôn trọng.

Giá trị tồn = SUM(current_quantity × unit_cost) của mọi lô, bao gồm phần chưa khả dụng. Đây là giá trị theo đơn giá cơ sở lưu tại lô, không phải giá thị trường, giá mua đề xuất hoặc giá vốn kế toán.

Báo cáo biến động giới hạn 93 ngày và 1.000 bản ghi; nếu vượt, yêu cầu thu hẹp phạm vi, không hiển thị tổng từ dữ liệu thiếu. Tổng hợp theo từng nguyên liệu và đơn vị cơ sở. CSV từ toàn bộ tập đã tải/lọc, không từ một trang API; escape nội dung và chặn spreadsheet formula injection. In chứng từ/bảng đang xem qua print CSS.

Các API đọc độc lập không cung cấp snapshot chung; báo cáo có thể thay đổi khi có giao dịch đồng thời. Chưa có endpoint aggregate để báo cáo kho lớn, tồn đầu/cuối kỳ, giá trị nhập–xuất, hiệu suất mua hoặc lịch sử giá. Không giả lập biểu đồ/KPI thiếu cơ sở.

## Backend gaps

1. Inventory Auth riêng đã hoạt động và bảo vệ 7 router; không còn chờ Auth Sales. Audit login/logout đã ghi vào bảng hiện hữu. Audit nghiệp vụ chung, Auth của Sales và kiểm chứng token Kho bị endpoint Sales từ chối vẫn là dependency riêng. Xem [chi tiết](inventory-auth-integration.md).
2. Catalog chỉ có status, chưa có API danh sách/tìm món. Công thức hiển thị các phiên bản có dish summary; tạo cho món mới cần nhập dish_id hợp lệ. Không thể thống kê toàn bộ món chưa có công thức.
3. Không có aggregate dashboard/report, lọc hết hạn/ngưỡng tồn trên server hoặc snapshot báo cáo nhất quán. Các phân tích giới hạn tập tải rõ ràng.
4. Lot/movement chỉ trả ID nguyên liệu và ID dòng chứng từ, không trả document ID. UI đọc metadata theo trang, deduplicate và giới hạn concurrency; không giả link từ dòng nhập sang ID phiếu. Đây là bổ sung schema response hữu ích về sau.
5. Danh sách stocktake thiếu counts/updated_at; tiến độ chỉ hiển thị khi mở detail. Không tự fetch từng detail để trang trí danh sách.
6. API lọc PO chỉ supplier/status; receipt lọc order/status/date. Không giả tìm toàn bộ theo mã/ngày từ một trang.
7. Không sửa phiếu nhập đã lập; nháp sai phải hủy và tạo lại. Không sửa công thức lịch sử; tạo phiên bản nháp mới.
8. Điều chỉnh/kiểm kê không vượt received_quantity của lô. Không thay constraint hoặc migration để vượt giới hạn.
9. Không có endpoint reverse ingredient→recipes, notification persistence, forecast, đa kho, trả hàng, barcode, import Excel, kế toán/công nợ.
10. Backend trả 422 tổng quát và chưa có request ID tiêu chuẩn.

Tiêu hao món chờ Sales/Kitchen: `ConsumptionService.consume_in_transaction` phải chạy trong transaction đánh dấu order item COMPLETED, đặt completed_at và có recipe_version_id đã pin; chỉ commit sau khi tiêu hao thành công. Người 1 cần ngăn xử lý lại transition đã hoàn thành; service hiện có cơ chế trả lại movement cũ khi retry để tránh trừ hai lần. Thiếu tồn phải báo lỗi rõ và rollback transaction hoàn thành món. Không nối vào thanh toán hoặc thêm endpoint Kitchen giả. `consume_completed_item` là service đã có; frontend chỉ xem movements CONSUMPTION hiện hữu. Đây là dependency tích hợp, không phải lỗi UI Kho.

## Chạy và kiểm thử

Từ `frontend`:

```powershell
npm.cmd install
npm.cmd run dev
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

`npm.cmd run dev` dùng adapter Inventory Auth thật. Backend cần secret riêng, database đã có user ACTIVE/hash bcrypt/quyền phù hợp. Không tự tạo user production và không dùng ID nhân viên hoặc chọn role để đăng nhập.

Đợt xây dựng giao diện Kho trước đã thêm dependency production `decimal.js` cho phép tính chính xác, Vitest + Testing Library + jsdom cho unit/component/API contract tests và Playwright cho browser QA. Đợt hoàn thiện layout/Auth này không thêm dependency npm. Không có UI kit, state manager hoặc chart library mới. Mock nằm trong tests và không được import bởi runtime production.

### Browser E2E: Auth và nghiệp vụ thật trên SQLite bộ nhớ

Không cần hoặc dùng `.env` backend. Từ repository root, dùng Python 3.11+ đã cài backend requirements:

```powershell
python frontend/e2e/demo_api.py
```

Script này vô hiệu dotenv và DATABASE_URL trước khi import app, dùng fixture SQLite in-memory có sẵn; chỉ bind 127.0.0.1:8011. Dữ liệu biến mất khi tắt server. Fixture có actor=1, supplier=1, nguyên liệu FLOUR=1/CHEESE=2, đơn vị G=1/KG=2, mapping=1/2 và món thử nghiệm=1. Các ID này chỉ dành cho server cô lập, không phải tài khoản production. Các API nghiệp vụ đi qua router/service/ORM thật; API này không bổ sung login/JWT giả cho backend.

Terminal thứ hai:

```powershell
cd frontend
npm.cmd run dev -- --config e2e/vite.config.ts
```

Frontend kiểm thử chạy ở http://localhost:5174, tắt đọc .env, proxy cố định tới SQLite 8011 và có cache riêng trong ignored tmp. Không alias adapter và không mock login/me/JWT. Các profile fixture chỉ tồn tại trong test database; production adapter gọi backend thật.

Terminal thứ ba trong `frontend`:

```powershell
npm.cmd run test:e2e
```

Playwright dùng Chrome đã cài. Suite kiểm tra marker môi trường có auth=inventory-real-backend trước thao tác. Auth dùng bcrypt/JWT thật và nghiệp vụ dùng router/service/ORM thật trên SQLite riêng. Không kiểm chứng deployment production hoặc PostgreSQL/Neon. Kết quả theo [checkpoint](inventory-ui-progress.md).

Nếu môi trường công cụ trên Windows không xóa được báo cáo cũ (`EPERM` với `.last-run.json`), chỉ định thư mục kết quả mới: `npm.cmd run test:e2e -- --output=../tmp/inventory-playwright-new-run`. Vitest giới hạn hai worker và tăng thời gian polling render cho máy chậm; không tắt kiểm thử hoặc tự retry để che lỗi.

### Luồng nghiệp vụ được kiểm tra trong harness

Tổng quan → nguyên liệu/đơn vị → tạo công thức cho dish_id=1, lưu các dòng và kích hoạt → nhà cung cấp/mapping → tạo PO hai dòng, nhập giá thỏa thuận → gửi duyệt → duyệt → xác nhận đã đặt → nhận một phần, nhập mã lô/hạn dùng → lưu DRAFT và chốt → xem PO PARTIALLY_RECEIVED, tồn và lô mới → nhận phần còn lại → xem PO RECEIVED → xuất một lượng nhỏ theo FEFO → xem biến động → tạo kiểm kê/chọn lô/bắt đầu → nhập actual, ghi lý do, xác nhận kể cả actual=0 → lưu → rà soát/chốt → quay lại dashboard.

Để kiểm tra conflict trên SQLite demo: bắt đầu kiểm kê, thay tồn cùng lô bằng một thao tác điều chỉnh riêng, sau đó lưu/chốt kiểm kê để nhận 409 và đối chiếu. SQLite không kiểm chứng row locking/concurrency PostgreSQL; cần PostgreSQL test riêng cho mức đó.

## Kết quả kiểm chứng

Xem inventory-ui-progress.md để biết lệnh đã chạy, số test và trạng thái Git. Auth thật đã kiểm chứng trên SQLite cô lập; không suy ra đã triển khai production hoặc xác minh dữ liệu Neon.
