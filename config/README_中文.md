# config

这里放配置模板、默认配置和配置说明。

不要提交本机密钥、账号、真实 token 或不可公开的环境变量。

## 当前配置

- `config.example.yaml` 默认使用 `transcription.provider: mock`，可直接用于 M1 mock 流水线。
- 真实密钥只通过 `.env` 或系统环境变量读取，配置文件只保存环境变量名。
- `audio` 视频转音频命令归属于 M1 音频准备能力；单独运行时不读取模型服务配置，通过命令行参数指定输出文件、采样率和声道数。

## 豆包语音识别

Web UI 选择 `豆包语音识别` 时，页面只需要填写豆包新版控制台 API Key。后端会把该 Key 放入当前进程的 `CLASS_UP_DOUBAO_API_KEY`，并自动使用：

- `transcription.provider: doubao`
- `transcription.endpoint: https://openspeech.bytedance.com`
- `transcription.model: bigmodel`
- `transcription.resource_id: volc.seedasr.auc`
- `upload.provider: sftp`

SFTP 上传信息不在页面填写，必须提前放在 `.env` 或系统环境变量中：

```dotenv
CLASS_UP_UPLOAD_HOST=
CLASS_UP_UPLOAD_USER=
CLASS_UP_UPLOAD_KEY_PATH=
```

`CLASS_UP_UPLOAD_KEY_PATH` 是本机 SSH 私钥文件路径，不是私钥内容。
