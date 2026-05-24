# SFTP 上传截断故障沉淀

## 背景

2026-05-24 排查真实 Doubao M1 转录失败时，发现任务 `outputs/3-1` 的前 6 个分段均已成功转录，第 7 个分段失败。

本地第 7 段音频完整：

```text
outputs/3-1/intermediate/segments/segment-0007.wav
size=13975302 bytes
duration=436.725s
```

服务器公网文件被截断：

```text
https://boneorbit.com/class-up/audio/3-1_segment-0007.wav
size=2293760 bytes
duration=71.677s
```

前 6 段本地和远端大小一致，例如第 6 段均为 `19200092 bytes`，所以问题集中在单次 SFTP 上传未完整落盘。

## 根因

旧实现只调用 `sftp.put(local_path, remote_path)`，没有在上传完成后校验远端文件大小。网络中断或 SFTP 写入异常导致远端残缺文件存在时，程序仍会继续把公网 URL 提交给 Doubao，最终表现为转录失败。

manifest 中第 7 段只记录了通用 `TRANSCRIPTION_FAILED`，`detail` 为空，说明底层网络/传输异常没有被明确包装，排查成本较高。

## 修复约定

- SFTP 上传后必须执行 `stat(remote_path)`，并要求 `remote_size == local_size`。
- 远端大小不一致时，尝试删除残缺远端文件，然后抛出可重试 `UploadError`。
- 分段转录以“上传 + Doubao submit/query + 结果转换”为完整重试单元。
- 重试次数沿用 `transcription.max_retries`，默认 3 次重试，即最多 4 次尝试。
- 每次失败要写入 segment 的 `retry_count` 和 `error.detail`，格式包含 `attempt=x/y`、`error_type` 和具体 detail。
- `httpx.TimeoutException` 与 `httpx.TransportError` 必须包装成可重试 `DoubaoTranscriptionError`，避免 manifest 中出现空 detail。

## 验证

新增/覆盖测试：

```text
tests/unit/test_sftp_upload.py
tests/unit/test_transcription_retry.py
tests/unit/test_doubao_network_retry.py
```

全量验证：

```powershell
python -m pytest
```

结果：

```text
31 passed
```

## 排查命令

对比本地和远端音频大小：

```powershell
Get-Item outputs\3-1\intermediate\segments\segment-0007.wav
curl.exe -I https://boneorbit.com/class-up/audio/3-1_segment-0007.wav
```

检查公网音频时长：

```powershell
ffprobe -v error -show_entries format=duration,size -of json https://boneorbit.com/class-up/audio/3-1_segment-0007.wav
```

检查服务器文件：

```bash
ls -lh /var/www/class-up/audio/3-1_segment-000*.wav
df -h /var/www/class-up/audio
```
