# 无痕AI API文档

> Status: v2.1\
> Last updated: 2026-04-20\
> 版本介绍：支持视频去水印和去字幕，视频消除与图片消除暂未上线。
> 详细文档：[无痕AI API文档](https://suiyu-network.feishu.cn/wiki/WUvXwI5vziT24qkAVdDcxTzLnef)


## 使用说明

无痕AI API由杭州岁羽网络科技有限公司开发与维护，通过API形式向客户输出业内领先的视频去水印/字幕，视频消除以及图片消除能力。在接入过程中，如果遇到问题，欢迎微信扫码联系技术支持。


## API版本与调用流程

### API使用准备

API Key是用于合法访问无痕AI API的唯一有效凭证。在开始正式使用API前，请**确保你已经拥有API Key**，如果还没有，请先联系技术支持，以获取你的专属API Key。**请妥善保管API Key，如果遗失或者泄漏，请及时联系我们的技术支持团队进行更换，并需要自行承担由此造成的一切损失**。

无痕AI API只负责对视频的处理，不负责存储，因此你**需要自己有存储系统（如OSS或者COS等）以及服务器**。API会自动从你指定的url中拉取视频或者图片进行处理；在处理过程中，通过callback同步处理进度和结果；并在处理完成后，自动上传到你指定的存储系统中。

### API的调用说明

**接口地址** https://api.wuhenai.com/v2/ 
**数据格式** application/json 
**字符编码** UTF-8 
**Header:** 除了user/accessToken接口，所有请求都必须携带Authorization。
**Query:** 必须携带nonce(随机字符串)和t(当前UTC时间，从1970/1/1秒数)参数。
**Response:** 所有接口返回的 JSON 数据均遵循以下结构：code, message, data (返回的业务数据，详情查看具体接口)


## User模块接口

User管理主要负责账号相关的操作，包括获取token、查询可用积分、查询积分充值与消费记录等。

### 获取 Access Token

除本接口外，API用户的所有请求都必须携带accesstoken。使用 API Key通过调用此接口，即可换取 access token。access_token的有效期是7天，过期后，接口调用会返回401错误，需再次调用此接口更新。

GET /user/access_token
- query
    - api_key: string, required, 对应账号的API Key，请向客服获取，通过官方邮件发送。注意保密。
- response
    - code: int, required, 状态码，0 表示成功，非 0 表示失败。
    - message: string, required, 处理结果提示信息：成功或者失败的原因。
    - data: object, required, 业务数据，详情查看具体接口。
    - data/expired: int, required, 过期的 UTC 时间戳（从 1970/1/1 起的秒数）。
    - data/access_token: string, required, access token，用于后续接口调用的认证。

### 获取账户信息

通过此接口，获取当前账户的可用积分数。

GET /user/me
- response
    - code: int, required, 状态码，0 表示成功，非 0 表示失败。
    - message: string, required, 处理结果提示信息：成功或者失败的原因。
    - data: object, required, 业务数据。
    - data/account_id: string, required, 唯一账户ID。
    - data/account_name: string, required, 账户名称。
    - data/balance: int, required, 账户的可用积分余额。


### 注册通知回调

无痕AI API通过此回调函数，通知任务的处理进度。

GET /user/notify_callback
- query
    - callback_url: string, required, 回调地址。
- response
    - code: int, required, 状态码，0 表示成功，非 0 表示失败。
    - message: string, required, 处理结果提示信息：成功或者失败的原因。
    - data: object, required, 业务数据。


### 查询账单（暂未开放）

无痕AI API通过此函数，查询近30天内的充值与消费账单。超过30天的账单，需通过客服人工导出。

GET /user/billings
- query
    - time_start: utc, optional, 账单查询开始时间。
    - time_stop: utc, optional, 账单查询结束时间。
- response
    - code: int, required, 状态码，0 表示成功，非 0 表示失败。
    - message: string, required, 处理结果提示信息：成功或者失败的原因。
    - data: object, required, 业务数据。
    - data/items: array, required, 符合条件的账单列表。
    - data/items/billing_id: string, required, 账单ID。
    - data/items/billing_type: string, required, 账单类型（free | buy_credits | consume | refund）。
    - data/items/credits: int, required, 积分增减情况（- 表示消耗，+ 表示增加）。
    - data/items/task_id: string, optional, billing_type=consume 时对应的 task_id。
    - data/items/task_type: string, optional, 任务类型（removeWatermark_vid | eraseObject_vid | eraseObject_pic）。
    - data/items/metering: string, optional, 任务的计费依据。
    - data/items/amout: int, optional, 支付金额（单位：元；仅支付类账单有值，其他类型为空或 0）。
    - data/items/create_at: int, required, 账单创建时间（UTC 秒）。

## 任务模块接口

任务模块主要负责任务的创建和管理。

### 视频去水印/字幕任务

无痕消除视频中通过后期包装添加的字幕，图形水印，LOGO水印，文字水印，移动水印等。

POST /video_removal
- request
    - video_url: string, required, 待处理的视频 url（过期时间尽量大点，建议 >1 天）。
    - model: string, optional, 处理模型（video_removal_std 默认 | video_removal_pro）。
    - method: string, optional, 处理方式（all_area 默认 | sel_area）。
    - rect: object, optional, method=sel_area 时标记待处理区域；格式 {\"x1\":100,\"y1\":200,\"x2\":500,\"y2\":600}；像素面积 width*height <= 480000。
    - upload_url: string, required, OSS/COS 等预签名上传 url（过期时间需 >24 小时），处理完成后 GPU 服务器 PUT 上传到此地址。
    - upload_headers: object, optional, GPU PUT 上传时附带的 Headers（如 {\"Content-Type\":\"application/octet-stream\"}）。
- response
    - code: int, required, 状态码，0 表示成功，非 0 表示失败。
    - message: string, required, 处理结果提示信息：成功或者失败的原因。
    - data: object, required, 业务数据。
    - data/task_id: string, required, 当前任务的ID。

### 视频消除任务（暂未开放）

消除视频中的原生内容，比如行走的人，移动的汽车，同时可以用来消除马赛克等遮挡，修复视频画面。

POST /video_eraser
- request
    - source_video: string, required, 待处理的视频 url（可下载链接，非播放链接）。
    - track_mode: string, required, 跟踪模式（no_tracking | auto_tracking）。
    - time_mask: int, required, custom_mask 标记的时间点（毫秒），从视频开始位置计算。
    - custom_mask: string(base64), required, 标记待消除区域的 mask。
    - upload_url: string, required, OSS/COS 等预签名上传 url（过期时间需 >24 小时），处理完成后 GPU 服务器 PUT 上传到此地址。
    - upload_headers: object, optional, GPU PUT 上传时附带的 Headers（如 {\"Content-Type\":\"application/octet-stream\"}）。
- response
    - code: int, required, 状态码，0 表示成功，非 0 表示失败。
    - message: string, required, 处理结果提示信息：成功或者失败的原因。
    - data: object, required, 业务数据。
    - data/task_id: string, required, 当前任务的ID。

### 图片消除任务（暂未开放）

消除图片中的水印、文字以及不想要的画面元素（如：戴着的眼镜，脸上的痣等）。

GET /photo_eraser
- request
    - source_img: string, required, 待消除的原始照片公网 url。
    - remove_option: string, required, 消除目标预设ID（PXC_1001 | PXC_1002 | PXC_1003 | PXC_1004 | PXC_1005）。
    - custom_prompt: string, optional, 用户自定义提示词（PXC_9000: 使用 custom_prompt）。
    - custom_mask: string(base64), optional, 用户自定义消除区 mask（PXC_0000: 使用 custom_mask）。
    - upload_url: string, required, OSS/COS 等预签名上传 url（过期时间需 >24 小时），处理完成后 GPU 服务器 PUT 上传到此地址。
    - upload_headers: object, optional, GPU PUT 上传时附带的 Headers（如 {\"Content-Type\":\"application/octet-stream\"}）。
- response
    - code: int, required, 状态码，0 表示成功，非 0 表示失败。
    - message: string, required, 处理结果提示信息：成功或者失败的原因。
    - data: object, required, 业务数据。
    - data/task_id: string, required, 当前任务的ID。

### 取消任务

取消排队中的任务，如果任务已经开始处理或者处理完成，此接口将返回失败。取消的任务不会扣除积分。

POST /cancel
- request
    - task_id: string, required, 需要取消的任务ID。
- response
    - code: int, required, 状态码，0 表示成功，非 0 表示失败。
    - message: string, required, 处理结果提示信息：成功或者失败的原因。
    - data: object, required, 业务数据。

### 任务回调

无痕AI API通过回调的方式来通知任务的处理进度以及状态变化。需要先完成注册。

回调函数的body结构如下：
- request
    - type: int, required, 消息类型。
    - msg: string, required, 处理消息。
    - data: object, required, 业务数据。
    - data/task_id: string, required, 回调的任务ID。
    - data/task_type: string, required, 当前任务的类型。
    - data/status: string, required, 当前任务的状态，详见下面状态表格。
    - data/progress: int, required, 任务进度（queued：前面排队任务数；processing：处理进度 0-100 整数）。
    - data/metering: int, optional, status=success 时计费依据（视频类：时长秒；图片类：张）。
    - data/credits: int, optional, status=success 时本次任务扣除的积分数。
    - data/description: string, optional, status=failed 时描述错误原因。


## 任务状态与异常code说明

**任务状态定义** 
- created：任务已创建，未启动 
- queued：任务已启动，正在排队等候处理 
- processing：任务正在处理中，进度 10%（下载） + 80%（处理） + 10%（上传）      
- success：处理完成，并上传到目标服务器成功 
- failed：任务处理失败 
- paused：任务被暂停（通过调用cancel接口） 



**异常code说明** 
| 0 | 成功 | 请求处理成功 |
| 1001 | 参数错误 | 缺少必填参数、参数格式不正确，或访问了无效路径 |
| 3001 | 积分不足 | 当前账号积分余额不足，无法创建任务 |
| 4001 | 资源错误 | 常见于工作流配置不存在 |
| 4003 | 用户不可用 | 当前用户不存在、已禁用，或状态不可继续使用 |
| 4004 | 任务不存在 | task_id 不存在，或该任务不属于当前用户 |
| 4005 | 任务不可取消 | 仅排队中的任务支持取消 |
| 401 | 未登录 | access_token 缺失、无效或已过期 |
| 7003 | API Key 无效或已禁用 | API Key 不存在、已禁用，或不属于可用状态 |
| 7004 | API Key 已过期 | API Key 已超过有效期，不能继续换取 access_token |
