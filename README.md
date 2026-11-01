# Genshin Macro

App Windows nhỏ chạy cạnh Genshin Impact để lưu và chạy macro bằng phím tắt.

## Hai kiểu macro

- **Spam phím**: bấm một phím liên tục (ví dụ F để skip cốt truyện). Chọn phím và khoảng cách giữa các lần bấm (ms). Chạy đến khi bạn bấm phím tắt lần nữa.
- **Ghi thao tác**: bấm **Ghi**, chuyển sang game, đánh combo thật (phím + chuột trái/phải), rồi bấm phím tắt của macro đó để dừng ghi. App lưu lại đúng nhịp để phát lại. Có thể tích **Lặp lại** để chạy vòng đến khi dừng.

Không ghi di chuyển chuột, chỉ ghi click trái/phải.

## Random ms

Ô **Random ms** ở dưới cùng áp dụng cho mọi macro. Mỗi khoảng chờ trước khi nhấn phím được cộng thêm một số ngẫu nhiên từ 0 đến giá trị này; thời gian giữ phím được cộng thêm từ 0 đến một phần ba giá trị này. Mặc định 100. Đặt 0 để tắt random (không khuyến khích).

## Cách dùng

1. Chạy `dist\GenshinMacro.exe` (hoặc `python main.py`). App **tự xin quyền Administrator** vì Genshin chạy ở quyền đó, nếu không game sẽ bỏ qua phím giả lập.
2. **Thêm Spam** hoặc **Thêm Ghi**, đặt tên, bấm ô **Phím tắt** rồi nhấn phím muốn gán (chuột phải vào ô để xóa).
3. Vào game, bấm phím tắt để chạy, bấm lại để dừng.

Lưu ý:
- Phím tắt không hoạt động khi cửa sổ app đang được focus.
- Macro tự dừng nếu bạn chuyển sang cửa sổ khác (Alt+Tab).
- Khi dừng, mọi phím đang giữ đều được nhả ra.
- Macro được lưu trong `macros.json` cạnh file exe.

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
