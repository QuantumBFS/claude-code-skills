---
name: download-koushare-lectures
description: Use when downloading a video or lecture from koushare.com (蔻享学术) — or a similar site whose pages are walled by a Tencent EdgeOne bot/CAPTCHA challenge while the video streams from Tencent VOD. Triggers/symptoms: curl on the page returns only a ~1KB EO_Bot_Ssid/__tst_status JS challenge, yt-dlp says "Unsupported URL", the page demands a "Security Verification" checkbox, or the stream URL contains voddrm.token / SimpleAES / a *.myqcloud.com .m3u8.
---

# Download Koushare Lectures (and other EdgeOne-walled Tencent-VOD video)

## Core insight

The **web page** is behind a Tencent EdgeOne bot wall (a JS cookie challenge, then a CAPTCHA). The **video stream** is not — it lives on a Tencent VOD CDN (`video-play.koushare.com` / `*.myqcloud.com`) protected only by a **signed token in the URL**. So don't fight the wall: get the signed CDN `.m3u8` URL by legitimate means, then download it with yt-dlp/ffmpeg. The stream is standard AES-128 HLS ("SimpleAES") with a fetchable key URI, which yt-dlp and ffmpeg decrypt natively.

This is *not* a DRM bypass. Tencent VOD's `voddrm.token` "SimpleAES" is HLS clientside encryption (a normal `#EXT-X-KEY:METHOD=AES-128` with a key served over HTTPS), not a license-server DRM like Widevine/FairPlay. Any HLS client that plays it can also save it. (Real DRM — Widevine/PlayReady/FairPlay — is a different beast and is out of scope; if you see a license-acquisition request to a DRM server and encrypted keys you can't fetch, stop.)

## When this applies (symptoms)

- `curl` on any `koushare.com` path → HTTP 200 but only ~1KB of obfuscated JS that sets `EO_Bot_Ssid` / `__tst_status` cookies and reloads.
- Page shows **"Security Verification — please check the box below"** (`TencentEOCaptchaWidget` from `captcha.eo.gtimg.com`).
- `yt-dlp <page-url>` → `ERROR: Unsupported URL` (no koushare extractor exists — 1700+ extractors, none match).
- The real stream URL looks like `https://video-play.koushare.com/.../voddrm.token.<JWT>.video_*.m3u8?sign=...&t=...&us=koushare2020`.

## Do NOT waste time on these — they dead-end

- ❌ Scraping the page or guessing API endpoints with curl. **Every** `koushare.com` path is EdgeOne-walled.
- ❌ Computing/forging the `EO_Bot_Ssid` cookie challenge. Even if you pass it, layer 2 is a Tencent CAPTCHA you cannot (and must not) solve. It's a dead end, not a shortcut.
- ❌ Hunting for a yt-dlp koushare extractor. There isn't one.

## Procedure

### 0. Ensure tools (once)

```bash
yt-dlp --version || pip3 install -q yt-dlp
ffmpeg -version | head -1 || brew install ffmpeg   # yt-dlp needs ffmpeg to mux HLS → mp4
```

### 1. Get the signed CDN stream URL

The page's video backend is a POST to `https://api-core.koushare.com/live/v2/live/playbackV2`; its JSON response holds the CDN URL. You need a browser that has passed the CAPTCHA. Two ways — pick by whether the Chrome extension is connected:

**Method A — user hands you the URL (no browser tooling needed):**
Ask the user to:
1. Open the lecture page in Chrome and click the verification checkbox so the video plays.
2. Press F12 → **Network** tab → type `m3u8` (or `mp4`) in the filter box.
3. Play the video for a second — a `.m3u8` request appears.
4. Right-click it → **Copy → Copy as cURL**, and paste that to you (it carries the URL and any cookies). Pasting just the `.m3u8` URL also works.

**Method B — drive the user's Chrome (if the claude-in-chrome extension is connected):**
1. `tabs_context_mcp`, create a tab, `navigate` to the page.
2. Ask the user to click the one "Security Verification" checkbox — **you must not click it yourself** (CAPTCHA/bot-detection is off-limits).
3. **Reload** the page, then `read_network_requests` filtered by `m3u8`. The media request fires early, so a reload *after* network tracking is active is what surfaces it. Fallbacks: read the `playbackV2` POST response body, or `read_page` for the `<video>` element's `src`. (The tab title after the CAPTCHA is the real lecture name — grab it for the filename.)

Either way you end up with a URL like:
`https://video-play.koushare.com/.../voddrm.token.<JWT>.video_1520228_0.m3u8?sign=...&t=...&us=koushare2020`

**Check the expiry.** The middle segment of `voddrm.token.<JWT>` is base64 JSON with `expireTimeStamp` — typically **~12h** from issue. Download promptly; the *URL* dies after that, but the downloaded *file* is permanent. To read it:
```bash
python3 -c 'import base64,json,sys; t=sys.argv[1]; t+="="*(-len(t)%4); print(json.loads(base64.urlsafe_b64decode(t)))' '<middle-token-segment>'
```

### 2. Download + decrypt

The URLs are long and full of `~` and `&` — write the URL to a file and use `yt-dlp -a` to avoid shell mangling. yt-dlp fetches fragments in parallel and decrypts the AES-128 stream natively:

```bash
printf '%s\n' 'PASTE_M3U8_URL_HERE' > url.txt
yt-dlp --no-playlist --concurrent-fragments 8 \
  --retries 10 --fragment-retries 20 \
  --user-agent "Mozilla/5.0" \
  -o "$HOME/Downloads/koushare_lecture.mp4" \
  -a url.txt
```

ffmpeg alternative (also follows the `#EXT-X-KEY` URI and decrypts): `ffmpeg -user_agent "Mozilla/5.0" -i "URL" -c copy out.mp4`

### 3. Verify

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 out.mp4 \
  | awk '{printf "%d min %d sec\n",$1/60,$1%60}'
ffprobe -v error -show_entries stream=codec_type,codec_name -of csv out.mp4
```
Confirm the duration matches the lecture and there's both a video (h264) and audio (aac) stream. Name the file from the real lecture title, not the numeric id.

## Quick reference

| Thing | Value |
|---|---|
| Page wall | Tencent EdgeOne: JS cookie challenge (`EO_Bot_Ssid` / `__tst_status`) → CAPTCHA (`TencentEOCaptchaWidget`, `captcha.eo.gtimg.com`) |
| Video backend API | `POST https://api-core.koushare.com/live/v2/live/playbackV2` (returns the CDN URL) |
| CDN (NOT walled) | `video-play.koushare.com`, `*.myqcloud.com` |
| Stream type | Tencent VOD HLS, `voddrm.token` + `SimpleAES` = standard AES-128, fetchable key URI + IV |
| Token life | ~12h (`expireTimeStamp` in the JWT middle segment) |
| Download | `yt-dlp --concurrent-fragments 8 -a url.txt` (or `ffmpeg -i URL -c copy out.mp4`) |

## Common mistakes

| Mistake | Fix |
|---|---|
| Trying to curl/scrape koushare.com pages or guess `/api/...` paths | Whole domain is EdgeOne-walled; only the CDN stream URL is reachable to a plain client. |
| Forging the EO_Bot cookie or solving the CAPTCHA | Prohibited and pointless — it dead-ends at CAPTCHA layer 2. Get the CDN URL via a real (user-driven) browser instead. |
| Calling `voddrm.token` "DRM" and giving up | It's HLS clientside AES-128 ("SimpleAES"), not license-server DRM — yt-dlp/ffmpeg decrypt it natively from the in-manifest key URI. |
| Passing the huge m3u8 URL inline on the CLI | Shell mangles `~` and `&`; write it to `url.txt` and use `yt-dlp -a url.txt`. |
| ffmpeg not installed | yt-dlp needs it to mux HLS → mp4: `brew install ffmpeg`. |
| Downloading after the token expired | Re-fetch a fresh m3u8 URL from the browser; tokens last ~12h. The already-downloaded file never expires. |
