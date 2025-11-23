# AstrBot Text2Image Service

[中文](README_zh-CN.md) | [English](README.md) | 日本語

## 機能

HTMLやテンプレートを画像に変換するシンプルなWebサービスで、画像のライフサイクル管理をサポートしています。

## 環境変数設定

- `PORT`: サービスポート、デフォルトは8999
- `IMAGE_LIFETIME_HOURS`: 画像の保持時間（時間単位）、デフォルトは24時間。この時間を超えた画像ファイルは自動的にクリーンアップされます

## API エンドポイント

### POST /text2img/generate

HTMLを画像に変換

> htmlとtmplのいずれかを選択してください。tmplとtmpldataは一緒に提供してください。

- `str` html: HTMLテキスト
- `str` tmpl: Jinja2 HTMLテンプレート
- `dict` tmpldata: Jinja2テンプレートデータ
- `bool` json: JSON形式で返すかどうか（idを返します）
- `dict` `optional` options
  - timeout (float, optional): スクリーンショットのタイムアウト時間。
  - type (Literal["jpeg", "png"], optional): スクリーンショットの画像タイプ。
  - quality (int, optional): スクリーンショットの品質、JPEG形式のみ適用されます。
  - omit_background (bool, optional): デフォルトの白い背景を非表示にするかどうか。これにより透明なスクリーンショットが可能になります（PNG形式のみ）。
  - full_page (bool, optional): ビューポートサイズだけでなく、ページ全体をキャプチャするかどうか、デフォルトはTrue。
  - clip (FloatRect, optional): スクリーンショット後にクリップする領域、xyは開始点です。
  - animations: (Literal["allow", "disabled"], optional): CSSアニメーションを許可するかどうか。
  - caret: (Literal["hide", "initial"], optional): `hide`に設定すると、スクリーンショット時にテキストキャレットが非表示になります。デフォルトは`hide`。
  - scale: (Literal["css", "device"], optional): ページのスケール設定。`css`に設定すると、デバイス解像度とCSSピクセルが1:1で対応し、高解像度画面ではスクリーンショットが小さくなります。`device`に設定すると、デバイスの画面スケール設定または現在のPlaywright Page/Contextのdevice_scale_factorパラメータに従ってスケールされます。
  - viewport_width (int, optional): スクリーンショットの幅を制御するカスタムビューポート幅。
  - device_scale_factor_level (Literal["normal", "high", "ultra"], optional): デバイスピクセル比レベル、デフォルトは"normal"。異なるレベルは独立したブラウザコンテキストプールを使用し、より良いパフォーマンスとリソース分離を提供します。
    - `normal`: デバイスピクセル比 1.0（デフォルト）
    - `high`: デバイスピクセル比 1.3
    - `ultra`: デバイスピクセル比 1.8
  - mask (List["Locator"]], optional): スクリーンショット時のマスクのLocatorを指定します。要素は#FF00FF色のボックスで覆われます。

### GET /text2img/data/{id}

idに対応する画像を返します。
