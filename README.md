# Tool Get Info Product

Cong cu local de tim video theo tu khoa san pham tren Facebook va Douyin, lay danh sach link, tai media khi can, sau do transcript noi dung video ra JSON.

## Tinh nang

- Mo trang tim kiem video Facebook theo tu khoa.
- Dich tu khoa tieng Viet sang tieng Trung de tim tren Douyin.
- Doc HTML da copy tu DevTools de trich xuat link video Facebook/Douyin.
- Tai audio Facebook bang `yt-dlp` va transcript bang `faster-whisper`.
- Tai video Douyin qua trinh duyet Coc Coc va icon download tren man hinh.
- Transcript video Douyin, tuy chon dich transcript sang tieng Viet.
- Co giao dien local tai `index.html`, chay qua `app.py`.

## Yeu cau

- Windows.
- Python 3.10+.
- `ffmpeg` co trong `PATH`.
- Trinh duyet Coc Coc neu dung luong tai Douyin tu dong.
- Mang internet de dich tu khoa, tai media va goi Google Translate endpoint.

## Cai dat

Tao virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Cai cac package Python can thiet:

```powershell
python -m pip install --upgrade pip
python -m pip install yt-dlp faster-whisper pyautogui opencv-python
```

Kiem tra `ffmpeg`:

```powershell
ffmpeg -version
```

Neu lenh tren khong chay, cai `ffmpeg` va them vao bien moi truong `PATH`.

## Chay giao dien local

```powershell
python app.py
```

Mo trinh duyet tai:

```text
http://127.0.0.1:8000/index.html
```

Co the doi port bang bien moi truong:

```powershell
$env:APP_PORT = "8080"
python app.py
```

## Quy trinh su dung

1. Nhap tu khoa san pham trong giao dien.
2. App se mo trang tim kiem Facebook va Douyin.
3. Copy HTML ket qua tim kiem tu DevTools va upload/paste vao giao dien neu can trich xuat link.
4. App xu ly link:
   - Facebook: tai audio vao `downloads/`, transcript ra `facebook_video_transcripts.json`.
   - Douyin: tai video vao `douyin_downloads/`, transcript ra `douyin_video_transcripts.json`.

## Chay bang command line

Tim Facebook:

```powershell
python facebook_search.py --keyword "dep"
```

Trich link Facebook tu HTML:

```powershell
python facebook_search.py --html facebook_page.html --output facebook_videos.json
```

Transcript Facebook:

```powershell
python transcribe_facebook_videos.py --input facebook_videos.json --output facebook_video_transcripts.json --cookies-from-browser chrome
```

Tim Douyin:

```powershell
python douyin_search.py --keyword "dep"
```

Dung tu khoa tieng Trung co san:

```powershell
python douyin_search.py --keyword "dep" --zh-keyword "<tu-khoa-tieng-trung>"
```

Trich link Douyin tu HTML:

```powershell
python douyin_search.py --html douyin_page.html --output douyin_videos.json
```

Tai video Douyin bang Coc Coc:

```powershell
python download_douyin_videos.py --input douyin_videos.json --output douyin_download_results.json --no-transcribe
```

Transcript Douyin:

```powershell
python transcribe_douyin_videos.py --input douyin_videos.json --download-results douyin_download_results.json --output douyin_video_transcripts.json
```

## File quan trong

- `app.py`: server local va API cho giao dien.
- `index.html`: giao dien web.
- `facebook_search.py`: mo tim kiem Facebook va parse HTML lay link video.
- `douyin_search.py`: dich tu khoa, mo tim kiem Douyin va parse HTML lay link video.
- `download_douyin_videos.py`: mo link Douyin bang Coc Coc va click icon download.
- `transcribe_facebook_videos.py`: tai audio Facebook va transcript.
- `transcribe_douyin_videos.py`: transcript video Douyin da tai.
- `rename_downloaded_files.py`: ho tro doi ten file da tai.
- `input`: file tu khoa hien tai.

## File dau ra

- `facebook_videos.json`: danh sach link video Facebook.
- `facebook_video_transcripts.json`: transcript Facebook.
- `douyin_videos.json`: danh sach link video Douyin.
- `douyin_download_results.json`: ket qua click tai Douyin.
- `douyin_video_transcripts.json`: transcript Douyin.
- `downloads/`: audio Facebook da tai.
- `douyin_downloads/`: media Douyin da tai.

`downloads/` va `douyin_downloads/` da duoc dua vao `.gitignore` vi la du lieu sinh ra khi chay tool.

## Luu y

- `faster-whisper` lan dau chay se tai model, nen co the mat thoi gian.
- Mac dinh Facebook transcript dung ngon ngu `vi`; Douyin transcript dung `zh` va dich sang `vi`.
- Neu Facebook can dang nhap, dung `--cookies-from-browser chrome`, `edge` hoac `firefox`.
- Luong tai Douyin phu thuoc giao dien Coc Coc va file mau `iconDownloadCocCoc.png`; neu Coc Coc doi UI, can cap nhat lai anh icon.
- Khong commit cac file media tai ve hoac file tam sinh ra trong qua trinh chay.
