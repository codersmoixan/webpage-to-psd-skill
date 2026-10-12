# webpage-to-psd 使用说明

将可在浏览器中渲染的网页转换为分层 Photoshop PSD。文字使用原生可编辑文字图层；图片、图标、背景、渐变和其他可见样式尽量独立分层。每份 PSD 表示指定宽度下的一个静态页面状态。

## 在 Codex 中使用

在消息中调用 `$webpage-to-psd`，提供网页地址或本地静态项目路径，并说明目标页面。对于已有 HTML 项目，保留 CSS、JavaScript、图片和字体的原始目录结构。

示例：

```text
$webpage-to-psd 将 D:/网站项目/preview 中的 pages/about.html 生成 PSD。
```

```text
$webpage-to-psd 将 https://example.com/about 生成 PSD，按 2560 像素视口宽度、一倍输出。
```

```text
$webpage-to-psd 将这个项目的 about 页面生成 PSD，视口宽度 2560，放大两倍，保留可编辑文字。
```

如需特定轮播图片、年份、标签页、弹窗或移动端宽度，请在请求中明确指定。只提供一张截图不适合本技能，需要可渲染的页面或项目。

## 当前默认值

| 项目 | 默认行为 |
| --- | --- |
| 捕获宽度 | 当前设备上 Codex／浏览器窗口所在屏幕的实际像素宽度；明确指定的宽度优先 |
| 输出倍率 | **1 倍**；请求放大时可使用 2、3、4 倍 |
| 分辨率 | 横向、纵向均为 **72 PPI** |
| 页面范围 | 完整页面，包含页脚 |
| 页面状态 | 当前／默认静态状态，不主动切换交互内容 |
| 本地项目 | 仅通过本机回环服务器渲染，不部署或上传项目 |

默认将屏幕像素宽度数值用作 CSS 视口宽度。屏幕宽度、浏览器视口宽度、页面内容宽度、输出倍率和 PPI 是独立概念。系统缩放不会被静默用来换算目标宽度。

例如：2560 × 6816 的捕获，一倍输出为 2560 × 6816，两倍输出为 5120 × 13632。修改 PPI 本身不会增加像素。当前脚本没有 `--ppi` 参数，采用 72 PPI；如需其他值，应同步调整导出配置、原生文字字号换算及验证。

浏览器滚动条可能占用内容宽度，技能会核对实际截图尺寸。若要求 PSD 精确为 2560 像素宽，必须明确处理滚动条差异，不会把 2545 当作 2560，也不会拉伸旧截图。屏幕读取失败或多屏定位不明确时，会询问所需宽度或显示器。

## 转换流程

1. 确定页面、视口宽度、倍率和静态状态。本地项目启动临时服务器，输出目录位于源项目之外。
2. 设置并验证浏览器视口，加载字体和可见图片；滚动加载延迟图片后回到目标位置。
3. 导出 DOM／样式、原始素材和整页参考图，并在截图前后比较页面结构，拒绝不稳定的捕获。
4. 准备独立图层与黑白图集，在浏览器中按最终倍率直接渲染文字、SVG 和 CSS 样式。
5. 从项目原始文件构建图片图层，生成 PSD、预览和验证报告。
6. 回读 PSD，验证画布、PPI、文字内容与边界，独立合成图层并进行视觉检查。
7. 交付文件，停止本次临时服务器，恢复临时视口设置。

这不是把一张整页截图放进 PSD，也不是直接放大已有的一倍文字截图。缺失原始图片、缺失非空文字快取、错误图集尺寸或不稳定捕获都会阻止导出。

## 输出文件

| 文件 | 内容 |
| --- | --- |
| `*.psd` | 分层 Photoshop 文件 |
| `*_preview.png` | 导出的完整页面预览 |
| 交付说明文件 | 尺寸、倍率、字体、状态和已知限制；名称按任务确定 |
| `PSD_validation.json` | 图层计数、原生文字、PPI、字体选择与合成误差 |
| `image_provenance.json` | 图片原文件来源及任何回退记录 |
| `capture_dimensions.json` | 屏幕／视口／截图／最终画布尺寸，由执行流程记录 |
| `visual_qa/` | 缩略总览、原生像素局部和质量摘要 |

## 手动运行脚本

以下为维护者用法。脚本不能代替浏览器捕获步骤，也不提供单条命令自动完成所有转换。需要 Python、`Pillow`、`numpy`、`psd-tools`，以及支持 DOM 提取、视口设置、截图和素材导出的浏览器工具。Codex 优先使用其内置 Python 环境。

在技能目录下执行，示例中的项目和输出路径需替换为实际路径：

```powershell
# Windows：读取显示器信息。
python -X utf8 scripts/read_display.py --output 'C:/PSD作业/device_display.json'

# 启动本地项目，使用它报告的 URL；保持此进程运行到素材取得完毕。
python -X utf8 scripts/serve_static_project.py --project-dir 'D:/网站项目/preview' --entry 'pages/about.html' --job-dir 'C:/PSD作业'
```

按 [浏览器捕获规范](references/browser-capture.md) 生成 `web_dom.json`、`web_dom_after.json`、`web_reference.png` 和 `web_assets.json` 后：

```powershell
python -X utf8 scripts/check_capture_pair.py --job-dir 'C:/PSD作业'
python -X utf8 scripts/build_psd.py prepare --job-dir 'C:/PSD作业'
```

`prepare` 默认一倍；明确要求两倍时使用：

```powershell
python -X utf8 scripts/build_psd.py prepare --job-dir 'C:/PSD作业' --render-scale 2 --strict-render-scale
```

随后用单独的回环服务器提供作业目录，在同一浏览器引擎中打开每个 `atlas_N_white.html` 和 `atlas_N_black.html`。按 `web_layers.json` 记录的宽度和高度设置视口，分别保存同名 PNG。确认所有图集尺寸和内容完整后执行：

```powershell
python -X utf8 scripts/build_psd.py build --job-dir 'C:/PSD作业' --template 'assets/text-template.psd' --output-name 'about.psd'
```

`build` 使用准备阶段记录的倍率，无需再次指定 `--render-scale`。标准 PSD 的单边限制为 30000 像素；明确请求的倍率须使用 `--strict-render-scale`，超限时不能静默缩小。

## 支持范围与限制

- 支持一个线性渐变叠加一个原始背景图片的独立拆层，并按捕获的伪元素顺序和 z-index 处理遮罩；复杂堆叠仍需视觉核对。
- 多重图片背景、混合模式和尚未支持的效果可能需要扩展直接渲染器。`--allow-image-raster-fallback` 仅用于已说明的复杂效果例外，不应作为日常默认参数。
- Canvas、视频或跨域嵌入内容可能使用局部栅格层，需在说明中标明。
- 原照片的像素数量限制实际细节，两倍导出不会创造新的照片细节。
- 编辑文字需要对应字体。字体替换会记录在报告中；浏览器和 PSD 回读验证不等于已在 Photoshop 内验证编辑和文字重排。
- 已编译的静态项目可直接使用。需要后端或构建过程的项目应先明确运行条件。

## 维护与检查

```powershell
python -X utf8 -m unittest discover -s scripts -p 'test_*.py'
```

详细执行规则见 [SKILL.md](SKILL.md)、[浏览器捕获规范](references/browser-capture.md) 和 [本地静态项目规范](references/local-static-project.md)。README 面向使用者；技能执行以这些文件和用户的明确要求为准。
