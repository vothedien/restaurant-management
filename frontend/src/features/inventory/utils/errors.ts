import axios from "axios";

const explanations: [RegExp, string][] = [
  [/Insufficient available stock/i, "Không đủ tồn khả dụng để xuất. Tải lại tồn kho và giảm số lượng hoặc nhập thêm hàng."],
  [/stock.*changed|stock.*moved|snapshot|movements.*after|movements.*since/i, "Tồn kho đã thay đổi từ khi bắt đầu kiểm kê. Giữ số đã đếm để đối chiếu, xem biến động rồi hủy và lập phiếu kiểm kê mới."],
  [/original received|schema change|exceeds.*received/i, "Số thực tế vượt lượng nhập ban đầu của lô. Hệ thống hiện chỉ cho điều chỉnh trong giới hạn lượng nhập gốc; kiểm tra lại số đếm."],
  [/remaining quantity/i, "Lượng nhận vượt phần còn lại của đơn mua. Phiếu khác có thể vừa được chốt; tải lại đơn và lập phiếu theo lượng còn thiếu."],
  [/already exists|duplicate|lot code/i, "Mã hoặc liên kết đã tồn tại. Kiểm tra bản ghi hiện có hoặc sử dụng mã khác."],
  [/Only draft|Only DRAFT|Only in-progress|cannot be cancelled|cannot be edited|invalid.*transition|cannot transition/i, "Chứng từ không còn ở trạng thái cho phép thao tác. Tải lại chi tiết để xem trạng thái mới nhất."],
  [/base unit.*(change|referenc)|referenced|in use|references|immutable/i, "Dữ liệu đã được tham chiếu trong công thức, nhà cung cấp hoặc lịch sử kho. Giữ nguyên thông tin nền và tạo bản ghi mới khi cần."],
  [/actor|user.*active|user not found/i, "Tài khoản thực hiện không còn hợp lệ hoặc đã ngừng hoạt động. Đăng nhập lại hoặc liên hệ quản trị viên."],
  [/must be active/i, "Nguyên liệu, đơn vị hoặc nhà cung cấp đã ngừng hoạt động. Chọn bản ghi đang hoạt động và tải lại danh mục."],
  [/conversion|matching dimensions/i, "Chưa có quy đổi trực tiếp phù hợp về đơn vị cơ sở. Kiểm tra đơn vị và cấu hình quy đổi."],
  [/minimum order/i, "Số lượng đặt chưa đạt mức đặt tối thiểu của nhà cung cấp."],
  [/not found/i, "Không tìm thấy dữ liệu được yêu cầu. Kiểm tra mã hoặc quay lại danh sách."],
  [/expired|manufacture date|receipt date|date.*precede|date range/i, "Ngày chứng từ hoặc hạn sử dụng không hợp lệ. Kiểm tra thứ tự ngày đặt, ngày nhận, ngày sản xuất và hạn dùng."],
];
export function errorInfo(error: unknown) {
  const status = axios.isAxiosError(error) ? error.response?.status : undefined;
  const raw = axios.isAxiosError(error) ? error.response?.data?.message : error instanceof Error ? error.message : "";
  const requestId = axios.isAxiosError(error) ? error.response?.headers?.["x-request-id"] : undefined;
  const known = typeof raw === "string" ? explanations.find(([pattern]) => pattern.test(raw))?.[1] : undefined;
  let message = known;
  if (status === 401) message = "Phiên làm việc không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại.";
  else if (status === 403) message = "Bạn không đủ quyền thực hiện thao tác này. Liên hệ quản lý để kiểm tra quyền truy cập.";
  else if (status === 404) message ||= "Không tìm thấy bản ghi. Bản ghi có thể đã bị xóa hoặc mã không đúng.";
  else if (status === 409) message ||= "Dữ liệu hoặc trạng thái chứng từ đã xung đột. Tải lại dữ liệu để đối chiếu trước khi thực hiện lại; nội dung chưa lưu vẫn được giữ.";
  else if (status === 400 || status === 422) message ||= "Dữ liệu chưa hợp lệ. Kiểm tra các trường bắt buộc, số lượng, đơn vị và ngày chứng từ.";
  else if (status && status >= 500) message = "Hệ thống chưa thể xử lý yêu cầu. Thử tải lại sau hoặc liên hệ quản trị viên.";
  else if (axios.isAxiosError(error) && !error.response) message = "Không kết nối được máy chủ. Kiểm tra kết nối và địa chỉ API, rồi thử tải lại.";
  // Locally generated validation messages are written for the operator.
  message ||= error instanceof Error && !axios.isAxiosError(error) ? error.message : "Không thể thực hiện yêu cầu. Vui lòng thử lại.";
  return { status, title: status === 409 ? "Cần đối chiếu dữ liệu" : status === 403 ? "Không đủ quyền truy cập" : "Không thể hoàn tất", message, requestId: typeof requestId === "string" ? requestId : undefined };
}
