# 和风天气接口生成工具

生成和风天气数据接口所需的认证信息与接口链接：

- 生成 Ed25519 私钥/公钥，签发 JWT（有效期最长 86400 秒）；
- 从和风天气控制台读取 API Host、开发者 ID、项目 ID、凭据 ID、API KEY；
- 在控制台创建或选用 API KEY 凭据、JWT 凭据；
- 按城市名查询 LocationID 与经纬度；
- 生成全部 16 个接口的 URL 与 curl 命令，可复制或导出 shell 脚本。

图形界面供日常使用，命令行工具可在 Windows 与 Linux 上批处理。

## 目录结构

```
weather/
├── README.md                      本文档
├── build_exe.py                   一键打包脚本（生成 dist/QWeatherAuth.exe）
├── dist/
│   ├── QWeatherAuth.exe           图形界面程序（打包产物）
│   └── data/                      凭据目录，程序运行时自动创建
├── src/
│   ├── qweather_core/             核心包：与界面无关的纯逻辑
│   │   ├── constants.py           程序名称、语言、指标类型、默认配置
│   │   ├── paths.py               凭据目录与各类文件路径、安全写入
│   │   ├── params.py              参数校验：经纬度、有效期、预报范围、POI、日期
│   │   ├── crypto.py              Ed25519 密钥对生成、公钥指纹、JWT 签发与解析
│   │   ├── endpoints.py           16 个接口的定义、请求上下文、URL 与 curl/shell 渲染
│   │   ├── config.py              config.json / auth.json 读写与旧格式兼容
│   │   └── http.py                请求发送、错误码说明、LocationID 查询
│   ├── qweather_console/          控制台包：登录态复用与凭据管理
│   │   ├── constants.py           控制台接口地址与枚举常量
│   │   ├── errors.py              ConsoleError
│   │   ├── cdp.py                 CDP 客户端（WebSocket 帧收发）
│   │   ├── browser.py             浏览器启动/发现、调试端口与本机状态
│   │   ├── payloads.py            请求体构造与纯数据整理
│   │   ├── session.py             ConsoleSession：页内 fetch 与凭据接口
│   │   ├── credentials.py         项目/凭据查询、创建与“一键生成”
│   │   ├── account.py             账号数据抓取与项目选择
│   │   └── cli.py                 命令行子命令
│   ├── qweather_gui/              图形界面包（tkinter）
│   │   ├── app.py                 主窗口，按区域组合下列 mixin
│   │   ├── constants.py           界面常量（标题、地址、各种延迟）
│   │   ├── theme.py               高分屏适配与窗口/任务栏图标
│   │   ├── main.py                界面入口
│   │   └── mixins/
│   │       ├── root.py            窗口骨架、滚动区、状态栏、通用对话框
│   │       ├── host.py            ① API Host 与位置
│   │       ├── auth.py            ② API KEY 与 JWT 输入
│   │       ├── links.py           ③ 链接生成与结果输出
│   │       ├── config.py          界面字段与配置文件的双向绑定
│   │       ├── location.py        地名查询与结果提示
│   │       ├── queues.py          后台线程结果轮询
│   │       ├── console.py         凭据管理窗口与一键生成
│   │       └── console_account.py 控制台参数自动读取与项目创建
│   ├── qweather_auth.py           命令行：keygen / api-key / jwt / links
│   ├── qweather_auth_gui.py       图形界面入口（薄，实现见 qweather_gui）
│   └── qweather_console.py        控制台命令行入口（薄，实现见 qweather_console）
├── tests/
│   ├── test_qweather_core.py      核心逻辑自检
│   └── test_qweather_console.py   控制台抓取与凭据创建自检
└── assets/
    └── icon.ico                   应用图标，打包时嵌入 exe 并用作窗口图标
```

## 运行环境

| 项目 | 要求 |
| --- | --- |
| 图形界面 | Windows，需要 Edge 或 Chrome（自动读取控制台时用其调试协议） |
| 命令行 | Windows / Linux，Python 3.8 及以上（实测 3.10.11 与 3.8.5） |
| 运行依赖 | `cryptography`（Ed25519 与证书解析） |
| 打包依赖 | `pyinstaller`；`pillow` 用于处理图标 |

```bash
python -m pip install cryptography
```

## 图形界面

运行 `dist/QWeatherAuth.exe`，或 `python src/qweather_auth_gui.py`。窗口标题为“和风天气接口生成工具”。

界面自上而下分四块。内容高于屏幕时，用**窗口右侧的竖向滚动条**上下拖动（鼠标滚轮也可滚动主体），状态栏固定在窗口底部。

### 1. API Host 与位置

| 控件 | 说明 |
| --- | --- |
| API Host | 控制台“设置”页中的 API Host，所有接口共用 |
| 打开控制台设置 | 用本工具的浏览器实例打开控制台；登录后界面参数自动出现 |
| 在系统浏览器打开 | 用系统默认浏览器打开控制台，不参与自动读取 |
| 查询地名 | 城市或区县名，如“深圳” |
| LocationID | 时光机接口必须使用；其余接口可用经纬度 |
| 立即查询 | 手动触发一次地名查询 |
| 纬度 / 经度 | 保留原始精度，最多 8 位小数，不四舍五入 |
| 语言 | 接口 `lang` 参数，默认 `zh` |

下列行为固定开启，界面上不提供开关：

- 输入停止 0.8 秒后自动查询 LocationID（少于 2 个字符不查询，与上次相同的城市名不重复查询）；
- 请求附带 `localTime=true`。

查询成功后提示行显示“已选地点：省 市 区（LocationID，经纬度）”。查询地名输入框保留使用者填写的原值，不覆盖。

若配置中有城市名但没有 LocationID，程序启动后会补查一次。

### 2. API KEY 认证

API KEY 输入框。请求时使用请求头 `X-QW-Api-Key`；凭据在“② JWT 认证”里的“凭据管理…”窗口中新建或选用。

### 3. JWT 认证

| 控件 | 说明 |
| --- | --- |
| 凭据 ID（kid） | 控制台中 JWT 凭据的 ID |
| 开发者 ID（iss） | 控制台“设置”页中的开发者 ID |
| 项目 ID（sub） | 控制台项目的 uniqueCode |
| 有效期（秒） | JWT 有效时间，取值 1 至 86400 |
| 凭据管理… | 打开凭据管理窗口（主窗口上只有这一个入口按钮） |

下方提示行显示当前私钥文件名，以及与私钥对应的公钥 SHA256，可与控制台显示值比对。

### 4. 一键生成所有接口链接

| 控件 | 说明 |
| --- | --- |
| 生成链接使用 | 选择 JWT 或 API KEY 认证 |
| 同时输出可执行的 curl 命令 | 生成结果中附加 curl 命令 |
| 预报天数 / 逐小时数 | v1 天气接口的 `days`（1-10）与 `hours`（1-240） |
| 指数类型 / 指数天数 | 天气指数接口的 `type` 与路径（1d / 3d） |
| 时光机日期 | 历史天气日期，格式 yyyyMMdd，限最近 10 天且不含今天 |
| 城市预报天数 / 城市小时数 | v7 城市版路径取值（3d/7d/10d/15d/30d、24h/72h/168h） |
| POI 类型 / POI 半径(km) | GeoAPI POI 的 `type`（scenic/TSTA）与 `radius`（1-50 公里） |
| 热门城市国家 | GeoAPI 热门城市的 `range`，ISO 3166 两位国家代码，留空表示不限 |
| 一键生成所有链接 | 生成 16 条链接 |
| 复制全部 | 复制生成结果到剪贴板 |
| 导出为 .sh 脚本 | 导出可执行 shell 脚本 |

生成链接时会同时写入 `auth.json`（JWT 模式还会写入 `jwt.txt`）并保存配置。

「生成结果」区域的长 URL 自动换行显示，不需要横向滚动；该区域本身可独立上下滚动。

## 自动获取控制台参数

程序启动 0.9 秒后尝试连接本机已运行的浏览器调试端口，读取控制台数据并填入界面。该过程：

- 只在已有可用调试端口时连接，不会自行启动浏览器；
- 连接后先判断登录状态，未登录则跳过，不弹窗提示；
- 成功后停止，失败则每 20 秒重试一次；
- 每三次重试才执行一次进程扫描（扫描需要调用 PowerShell，降低频率以减少开销）；
- 调用 PowerShell 与 taskkill 时带 `CREATE_NO_WINDOW`，不会出现控制台黑窗口。

若尚未登录，点“打开控制台设置”：程序启动或复用本工具的浏览器实例打开控制台，登录完成后自动读取并填写 API Host、开发者 ID、项目 ID、凭据 ID、API KEY，并弹窗显示账号与项目信息。

若账号下还没有项目，程序不会报错，而是弹出只要求填写项目名的对话框，确认后自动在控制台创建该项目，并把新项目 ID 写入界面；随后可用“凭据管理…”创建凭据。

读取时会取出控制台中 JWT 凭据已上传公钥的 SHA256，与本地私钥对应公钥的指纹比对，在弹窗中说明 JWT 是否可用。

## 凭据管理窗口

“② JWT 认证”里的“凭据管理…”打开该窗口（主窗口只保留这一个入口）。

窗口左侧为项目列表，右侧为该项目的凭据列表。

- 打开后自动选中第一个项目，并在右侧加载其凭据；点其他项目，右侧随之刷新；
- 账号下没有项目时，左下角出现“没有项目？新建”输入框，点“创建”后窗口内刷新并选中新项目。

底部按钮：

| 按钮 | 行为 |
| --- | --- |
| 一键生成 | 把该项目该有的凭据一次备齐：JWT 凭据（用本地公钥，没有密钥对时先生成）与 API KEY 凭据；两者都会先检查项目里是否已有，已有的直接复用，不重复创建。完成后把凭据 ID、API KEY 填进界面并保存 |
| 重新生成密钥 | 生成新的 Ed25519 密钥对，文件名含时间戳，不覆盖旧文件；之后点“一键生成”会用新公钥创建 JWT 凭据 |
| 取消 | 关闭窗口 |
| 打开公钥目录 | 打开凭据目录 |
| 控制台项目管理 | 用系统浏览器打开控制台项目管理页 |

右侧凭据列表**双击某一条**可以直接选用它（不修改控制台）：选到 JWT 凭据会核对公钥与本地私钥，
选到 API KEY 凭据会把明文密钥填入界面并保存到 `auth.json`（不修改 kid）。

关于多项目：**同一个公钥在控制台只能注册到一个凭据上**（重复注册会返回 `code=122 PublicKeyExist`）。
因此工具按项目分别管理密钥对：项目首次创建 JWT 凭据时会记下使用的密钥，
之后在该项目点“一键生成”会先切回这把密钥；若公钥已被别的项目占用，会自动生成一把新密钥重试，
并把“项目 → 密钥”的对应关系记在配置里。签发 JWT 前也会按项目切换密钥，避免签出用不上的令牌。

新建凭据（由“一键生成”触发）的规则：

- 名字为“前缀 + 年月日时分秒”，同名前缀已占用时追加 `-1`、`-2`；
- JWT 凭据前缀为 `jwb`（如 `jwb20261015191705`），API KEY 凭据前缀为 `api`（如 `api20261015191649`）；
- 启用哪些 API 沿用项目中已有凭据的设置；若项目中还没有凭据，则启用免费套餐的 8 个 API：天气预报、GeoAPI、分钟降水、天气预警、天气指数、空气质量、时光机、天文；
- 创建后追加设置“允许获取控制台数据”（财务汇总、请求量统计）；
- 是否可复用按“控制台记录的公钥 SHA256 = 本地公钥指纹”判断，命中就不新建。

控制台不提供修改已有凭据公钥的功能，更换密钥的方式是：点“重新生成密钥”生成新密钥，再到凭据管理窗口点“一键生成”。旧凭据需在控制台删除，删除操作需要邮箱验证码。

## 数据文件与配置

凭据目录与程序同目录，名为 `data`：运行 `dist/QWeatherAuth.exe` 时是 `dist/data/`，运行 `src/*.py` 时是 `src/data/`。可用环境变量 `QWEATHER_DATA_DIR` 指定其他位置。

| 文件 | 内容 |
| --- | --- |
| `config.json` | 界面字段与接口参数，明文 |
| `auth.json` | 当前认证信息（请求头名与取值），权限 0600 |
| `jwt.txt` | 最近一次签发的 JWT，权限 0600 |
| `ed25519-private-<时间戳>.pem` | Ed25519 私钥 |
| `ed25519-public-<时间戳>.pem` | Ed25519 公钥 |

`config.json` 字段：

| 字段 | 默认值 | 含义 |
| --- | --- | --- |
| `api_host` | 空 | API Host |
| `latitude` / `longitude` | 22.53 / 113.94 | 经纬度 |
| `lang` | `zh` | 接口语言 |
| `location_name` | 深圳 | 查询地名 |
| `location_label` | 空 | 已选地点提示文本 |
| `location_id` | 空 | LocationID |
| `local_time` | true | 是否附加 `localTime=true` |
| `auth_mode` | `jwt` | 生成链接使用的认证方式 |
| `credential_id` | 空 | JWT 凭据 ID（kid） |
| `developer_id` | 空 | 开发者 ID（iss） |
| `project_id` | 空 | 项目 ID（sub） |
| `jwt_lifetime` | 900 | JWT 有效期（秒） |
| `credential_name_prefix` | `jwb` | JWT 凭据名前缀（界面不再提供修改，固定 `jwb`；API KEY 固定 `api`） |
| `project_keys` | `{}` | 项目 ID → 该项目使用的私钥文件名（多项目时各自一把密钥） |
| `forecast_days` | 3 | 每日预报天数 |
| `forecast_hours` | 24 | 逐小时预报小时数 |
| `indices_type` | 0 | 天气指数类型，0 为全部 |
| `indices_days` | `1d` | 指数预报天数，1d 或 3d |
| `time_machine_date` | 空 | 时光机日期 |
| `geo_range` | `cn` | 热门城市国家代码 |
| `poi_type` | `scenic` | POI 类型 |
| `poi_radius_km` | 5 | POI 搜索半径（公里） |
| `city_forecast_days` | `3d` | v7 城市每日预报路径 |
| `city_forecast_hours` | `24h` | v7 城市小时预报路径 |

## 接口清单

| 服务 | 方法与路径 | 关键参数 |
| --- | --- | --- |
| GeoAPI 城市搜索 | `GET /geo/v2/city/lookup` | `location`、`number`、`lang` |
| GeoAPI 热门城市 | `GET /geo/v2/city/top` | `range`、`number`、`lang` |
| GeoAPI POI 搜索 | `GET /geo/v2/poi/lookup` | `location`、`type`、`number`、`lang` |
| GeoAPI POI 范围搜索 | `GET /geo/v2/poi/range` | `location`、`type`、`radius`、`number`、`lang` |
| 实时天气 | `GET /weather/v1/current/{lat}/{lon}` | `localTime`、`lang` |
| 每日天气预报 | `GET /weather/v1/daily/{lat}/{lon}` | `days`、`localTime`、`lang` |
| 逐小时天气预报 | `GET /weather/v1/hourly/{lat}/{lon}` | `hours`、`localTime`、`lang` |
| 城市实时天气 | `GET /v7/weather/now` | `location`、`lang` |
| 城市每日预报 | `GET /v7/weather/{days}` | `location`、`lang` |
| 城市小时预报 | `GET /v7/weather/{hours}` | `location`、`lang` |
| 分钟级降水 | `GET /v7/minutely/5m` | `location`（经度,纬度）、`lang` |
| 实时空气质量 | `GET /airquality/v1/current/{lat}/{lon}` | `lang` |
| 每日空气质量 | `GET /airquality/v1/daily/{lat}/{lon}` | `lang` |
| 实时天气预警 | `GET /weatheralert/v1/current/{lat}/{lon}` | `localTime`、`lang` |
| 天气生活指数 | `GET /v7/indices/{1d\|3d}` | `type`、`location`、`lang` |
| 时光机（历史天气） | `GET /v7/historical/weather` | `location`（仅 LocationID）、`date`、`lang` |

说明：

- 路径版本不统一：weather、airquality、weatheralert 为 `v1`，GeoAPI 为 `v2`，分钟降水、天气指数、时光机仍为 `v7`。
- 三条“城市”开头的天气接口属于 WebAPI v7，官方已标记弃用，停服日期 2027-06-01；新项目建议使用对应的 `v1` 接口。生成结果中会标注“官方已弃用”。
- 经纬度：官方文档写“最多两位小数”，实测各接口对 8 位小数均返回 200，且 GeoAPI 返回的坐标本身为 5 位小数，因此工具原样保留精度（最多 8 位，去掉多余的 0）。
- 时光机只接受 LocationID，先用 GeoAPI 查询后填入。
- POI 搜索与 POI 范围搜索的 `type` 只支持 `scenic`（景点）与 `TSTA`（潮汐站点）；`radius` 单位为公里。POI 范围搜索在部分坐标会返回 `No Such Location`，同坐标的 POI 搜索正常，可更换坐标或增大半径。
- 错误按 HTTP 状态码判断（400/401/403/404/429/500），响应体为 `application/problem+json`；遇到 429 应退避重试，持续的错误请求可能导致账号被冻结。
- 实时天气返回的 `humidity`、`cloudCover` 是 0 至 1 的小数，不是百分比。
- 数据展示需按官方要求注明来源“天气服务由和风天气驱动”。

## 命令行

### qweather_auth.py

```bash
python src/qweather_auth.py keygen                        # 生成 Ed25519 密钥对
python src/qweather_auth.py keygen --force                # 已有密钥时也重新生成
python src/qweather_auth.py api-key <API_KEY>             # 写入 API KEY
python src/qweather_auth.py jwt <凭据ID>                  # 生成 JWT 并写入凭据
python src/qweather_auth.py links                         # 输出全部接口链接
python src/qweather_auth.py links --shell                 # 输出可执行的 shell 脚本
python src/qweather_auth.py links --mode api_key --no-curl  # 仅输出 URL
```

`links` 可用参数：`--host --lat --lon --city --location-id --lang --mode --kid --days --hours --date --no-curl --shell`。

### qweather_console.py

```bash
python src/qweather_console.py login --save                          # 登录控制台并写入 config.json
python src/qweather_console.py login --json out.json                 # 完整数据导出为 JSON
python src/qweather_console.py create-project <项目名> --save         # 账号下没有项目时创建
python src/qweather_console.py publish --public-key <公钥.pem> --save # 创建 JWT 凭据
python src/qweather_console.py api-key --save                        # 确保有可用的 API KEY 凭据（已有则复用）
python src/qweather_console.py discover --out console_dump           # 导出控制台页面数据（排查用）
```

`publish` 会先检查控制台是否已有与公钥匹配的 JWT 凭据，有则复用；`--prefix` 可指定新凭据名前缀。

## 控制台登录实现

- 程序调用本机的 Edge 或 Chrome，以独立配置目录与调试端口启动，通过 CDP（WebSocket + HTTP）控制页面；
- 控制台数据通过页面内 `fetch` 调用控制台自身的 `/v2/rest` 接口获取，携带浏览器中的登录 Cookie，不解析页面 DOM；
- 不使用、不保存账号密码，登录始终在浏览器窗口中由使用者完成；
- 浏览器配置目录位于本机 `%LOCALAPPDATA%\QWeatherTool\browser-profile`，不写入项目目录；删除该目录即退出登录；
- 调试端口记录在 `%LOCALAPPDATA%\QWeatherTool\cdp.json`，端口失效时程序会读取浏览器的 `DevToolsActivePort` 文件，或扫描浏览器进程命令行获取。

## 自检

```bash
python -m unittest discover tests
```

共 93 项用例，覆盖接口表与链接渲染、坐标与参数校验、配置读写、JWT 签发与解析、控制台数据提取、凭据创建请求体、进程调用参数等。其中 1 项涉及 PowerShell 进程调用的用例仅适用于 Windows，在其他平台自动跳过。

## 重新打包 exe

项目根目录已提供一键打包脚本 `build_exe.py`，直接运行即可：

```bash
python build_exe.py            # 打包到 dist/QWeatherAuth.exe
python build_exe.py --verify   # 打包后再启动一次，确认能正常打开
python build_exe.py --keep     # 保留 build/ 中间产物（排查用）
```

脚本会依次完成：检查入口与图标 → 缺 PyInstaller 时自动安装 → 关闭正在运行的 `QWeatherAuth.exe`
→ 调用 PyInstaller 打包，产物留在 `dist/` → 清理 `build/` 与 `*.spec`。`dist/data/` 是运行时的凭据目录，不会被清理。

也可以手工执行 PyInstaller：

```bash
python -m PyInstaller --noconfirm --onefile --windowed --name QWeatherAuth ^
    --icon assets\icon.ico --add-data "assets\icon.ico;." ^
    --distpath dist --workpath build --specpath . src\qweather_auth_gui.py
```

`--add-data` 将图标嵌入 exe，运行时用于设置窗口与任务栏图标。手工打包同样需要先关闭正在运行的 `QWeatherAuth.exe`。

## 已知限制

- 控制台不提供修改已有凭据公钥的接口，更换密钥需新建凭据，旧凭据只能在控制台删除（需邮箱验证码）。
- 控制台接口为前端私有接口，控制台改版后可能需要调整。
- WebAPI v7 的城市天气接口处于弃用期（2027-06-01 停服）。
- JWT 有效期上限为 86400 秒，不适合作为长期凭据保存。
- POI 范围搜索依赖控制台侧 POI 数据，部分坐标无数据。

## 安全提醒

- `data/` 目录内含私钥与明文凭据，不要提交到版本库，也不要在共享目录中长期留存。
- API KEY 建议定期在控制台轮换。
