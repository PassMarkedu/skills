# 安装 PassMarkedu A-level 阅卷 Skill

基于 [PassMarkedu A-level](https://passmarkedu.com) 的官方真题与评分标准服务，在你使用的 AI 应用中批改答卷并生成 PDF。完整介绍、支持年份和常见问题：https://passmarkedu.com/marking-kit#faq 。

## 复制安装指令

把下面这句话发给支持本地 Skill 的 AI 应用：

> 请帮我安装 PassMarkedu A-level 阅卷 Skill：从 https://passmarkedu.com/skills/passmarkedu-marking.zip 下载，解压后把 passmarkedu-marking 文件夹放到你的 Skill 目录。安装成功后，读取 SKILL.md 和 references/onboarding.md，展示欢迎介绍并引导我连接账号；用接口实际返回的授权链接和授权码，不要使用示例值。若已保存授权则保留，不重复登录。

也可以下载 zip，按所用应用的 Skill 安装方式导入。安装目录和联网权限因应用而异，以该应用的说明为准。

本地开发站点下载的 ZIP 已带该站点的 `origin.txt`，安装后直接读取 `SKILL.md`。仅手动切换服务地址时运行：

```bash
python3 /path/to/passmarkedu-marking/scripts/config.py set-origin http://localhost:5173
```

将示例 URL 换成浏览器地址栏的实际 origin（协议、主机和端口，不带路径）。这个非敏感配置保存在 Skill 目录的 `origin.txt`，重新打开 WorkBuddy 仍生效。切换站点后须重新连接该站点账号；不同站点不会共用授权。

## 命令行安装

需要 Node.js 和 GitHub 网络访问：

```bash
npx skills@latest add PassMarkedu/skills
```

命令行只负责安装文件。完成后在 AI 对话中说「启用 passmarkedu-marking，介绍并连接账号」，即可开始首次使用流程。

## 第一次使用

安装后的欢迎消息会先给出真实授权链接。登录或注册账号，核对授权码并点击「授权」；回到对话，AI 会自动完成连接。不要在对话里发送密码、短信验证码或访问令牌。之后上传答卷 PDF 或按页排序的照片，说「帮我批改这份答卷」。

支持 Edexcel IAL 数学、进阶数学、物理、化学、经济、会计、生物，以及 CAIE AS & A Level 数学、进阶数学、物理、化学、经济、会计、计算机科学。只批改已收录并开放批改的官方真题及配套评分标准；具体试卷或小问暂不支持时，会在开始前说明。

免费账号可批 1 份整卷和 5 道单题（拍照或拼题卷按题计），订阅后不限次。批过的卷子或题目重新批改、改分都不再占用次数。交付三份 PDF：批改答卷在原卷上以红色标出分数和得分点；阅卷结果包含得分总览、主要失分点、逐题错误说明、正确解法和官方评分标准；复核说明只列 AI 拿不准、需要你来定的地方，要改就回复「第 N 处改成 X 分」。整卷答卷首页列出总分、等级及对应考季分数线；拼题卷只列得分和满分。改分后三份 PDF 同步更新。

使用能够看图、联网、处理文件且推理能力较强的模型；能选择推理强度时建议使用高强度。弱模型可能误读手写或混淆评分标准与卷面。

## 1.9 流程工具

新版随包提供 `scripts/workflow.py`：一次准备材料，批量看图、统一裁剪并保存必要证据，试算后按实际失分生成解释，再下载批改答卷、阅卷结果和复核说明三份 PDF。常规路径需要 Python 3；图像准备复用应用已有的 PDF 工具，不自动安装依赖。模型直接查看本题作答与官方 MS，仍负责每个得分点的判断及疑点复核。工具用法由 Skill 引导，无需使用者手动编写请求。不同模型仍可能因字迹识别和规则判断产生分差；相同证据与相同评分数据由服务端按同一规则计分。
