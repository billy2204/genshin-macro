# Genshin Macro

App Windows nhỏ chạy cạnh Genshin Impact để lưu và chạy macro bằng phím tắt.

## Hai kiểu macro

- **Spam phím**: bấm một phím liên tục (ví dụ F để skip cốt truyện). Chọn phím và khoảng cách giữa các lần bấm (ms). Chạy đến khi bạn bấm phím tắt lần nữa.
- **Ghi thao tác**: ghi lại combo thật (phím + chuột trái/phải) kèm nhịp thời gian, rồi phát lại. Có thể tích **Lặp lại** để chạy vòng đến khi dừng. Danh sách **Thao tác đã ghi** hiển thị từng bước: thời gian, nhấn/nhả, phím nào.

Không ghi di chuyển chuột, chỉ ghi click trái/phải.

## Ghi một combo

1. Chọn (hoặc thêm) một macro kiểu Ghi trong danh sách bên trái.
2. Đặt **Phím Ghi** ở thanh dưới cùng (ví dụ F10). Đây là phím ghi chung cho toàn app.
3. Vào game, bấm Phím Ghi. Overlay hiện **● GHI: tên macro**.
4. Đánh combo. Bấm Phím Ghi lần nữa (hoặc phím tắt của chính macro đó) để dừng. Phím dừng không bị lưu vào combo.
5. Quay lại app xem danh sách thao tác, tích Lặp lại nếu cần.

Nếu bạn Alt+Tab ra khỏi game trong lúc ghi, mọi thao tác từ lúc đó bị bỏ qua (Alt+Tab không bị ghi).

### Phím bỏ qua

Mỗi macro Ghi có danh sách **Phím bỏ qua**: những phím này không bao giờ bị ghi (mặc định W A S D để di chuyển không lọt vào combo). Bấm **+ Thêm phím** rồi nhấn phím muốn bỏ qua, hoặc chọn một phím trong danh sách và bấm **− Bỏ phím đã chọn**.

### Sửa từng thao tác

Bảng **Thao tác đã ghi** hiện cột **Chờ (ms)**: thời gian chờ kể từ thao tác trước. Dòng **Tổng** là tổng thời gian cả macro. Chọn một dòng, sửa **Chờ**, **Nhấn/Nhả**, loại (Phím / Chuột trái / Chuột phải, với Phím thì bấm nút phím rồi nhấn phím mới) và bấm **Áp dụng**. Đổi thời gian chờ của một dòng thì các dòng sau dịch theo. **Xóa event** bỏ dòng đang chọn, các dòng sau giữ nguyên mốc thời gian. Lưu ý nếu xóa một lần Nhấn mà giữ lại Nhả thì phím đó coi như không được bấm; macro vẫn nhả mọi phím đang giữ khi dừng.

## Nhập macro từ Razer Synapse

Nút **Nhập Razer…** chọn file .xml xuất từ Razer Synapse (Macro, Export). App đọc phím, chuột trái/phải, thời gian chờ và khối lặp, tạo thành một macro Ghi mới có thể sửa như bình thường. Di chuyển chuột và nút chuột giữa bị bỏ qua.

## File macro

Thanh trên cùng có **Mở file…** và **Lưu thành…** để chọn đường dẫn file macro (.json). App nhớ file đang dùng trong `settings.json` cạnh exe, lần sau mở lại đúng file đó. Muốn chia sẻ macro sang máy khác chỉ cần copy file .json rồi Mở file… trên máy kia.

## Overlay

Một khung nhỏ luôn nổi trên cùng, góc trên trái màn hình, hiện **Sẵn sàng** / **● GHI: tên** / **▶ tên**. Kéo thả để di chuyển. Click vào overlay không làm game mất focus. Bật tắt bằng ô **Overlay** ở thanh dưới. Lưu ý: nếu game chạy chế độ Fullscreen độc quyền thì overlay có thể bị che, hãy dùng Borderless/Windowed.

## Random ms

Ô **Random ms** áp dụng cho mọi macro. Mỗi khoảng chờ trước khi nhấn phím được cộng thêm một số ngẫu nhiên từ 0 đến giá trị này; thời gian giữ phím được cộng thêm từ 0 đến một phần ba giá trị này. Mặc định 100. Đặt 0 để tắt random (không khuyến khích).

## Cách dùng

1. Chạy `dist\GenshinMacro.exe` (hoặc `python main.py`). App **tự xin quyền Administrator** vì Genshin chạy ở quyền đó, nếu không game sẽ bỏ qua phím giả lập.
2. **Thêm Spam** hoặc **Thêm Ghi**, đặt tên, bấm ô **Phím tắt** rồi nhấn phím muốn gán (chuột phải vào ô để xóa).
3. Vào game, bấm phím tắt để chạy, bấm lại để dừng.

Lưu ý:
- Phím tắt không hoạt động khi cửa sổ app (hoặc hộp thoại của app) đang được focus.
- Macro tự dừng ngay nếu bạn chuyển sang cửa sổ khác (Alt+Tab), và nhả hết phím đang giữ.
- Mặc định macro lưu trong `macros.json` cạnh file exe (đổi được bằng Lưu thành…). Nếu file hỏng, app sao nó thành `.bak` và bắt đầu lại từ trống.

## Cập nhật app

Nút **Cập nhật** trên thanh công cụ: một bấm là tự kiểm tra GitHub Releases của repo này (file `manifest.json`), có bản mới thì tải về, app tự tắt, thay file exe và mở lại, không hỏi gì thêm. Chuột phải vào nút để đổi nguồn cập nhật hoặc **Chọn file .exe…** đã tải sẵn. Nguồn cập nhật lưu trong `settings.json`. Repo phải ở chế độ public thì link tải mới hoạt động không cần đăng nhập.

Phát hành bản mới: tăng `APP_VERSION` trong `genshin_macro/updater.py`, build, rồi tạo release có hai file `GenshinMacro.exe` và `manifest.json` (`{"version": "x.y.z", "url": "<link tải GenshinMacro.exe>"}`).

## Build

```bat
build.bat
```

Cần Python 3.10+. Kết quả: `dist\GenshinMacro.exe`.

## Test

```bat
python -m pytest
```

## Cảnh báo

Genshin Impact có chống gian lận và điều khoản cấm công cụ bên thứ ba. App không can thiệp vào game, chỉ gửi phím như bàn phím thật, nhưng dùng macro vẫn có rủi ro với tài khoản. Tự cân nhắc.
