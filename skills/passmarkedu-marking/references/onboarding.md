# Installation welcome and account connection

Read this after successfully installing the skill, or when the user asks to start/connect. Only say “已安装成功” when this run actually verified a successful installation; otherwise use “欢迎使用 PassMarkedu A-level 阅卷 Skill”。 Use the user's language (Chinese example below; translate for English). The service display name is **PassMarkedu A-level**; its website, account system, API, repository, skill id and token paths remain `passmarkedu.com` / `passmarkedu-marking` as documented in SKILL.md.

1. Confirm installation only after the files are installed and readable. Resolve the installed origin and its token using SKILL.md §0 before requesting a device code. An update preserves that origin's authorisation; a new origin has its own account connection. Do not check for, install, or ask the user to install PDF rendering tools or any other package: the helper finds them itself (Homebrew folders included) and `start` reports `renderer`.
2. If there is no saved token, obtain a device code using §1, then send the welcome below with the **actual** `verification_uri_complete` and `user_code`. The example's angle-bracket values are placeholders, never links/codes to display. Do not ask for a scan first or ask the user to paste a password, SMS code or access token. Poll and save the token as §1 directs. Authorisation is required before marking, not before reading the introduction.
3. If a token already exists, replace the account section with “已找到保存的账号授权，可以直接上传答卷开始批改。” A file's presence does not prove authorisation is still valid; handle 401 through §1 when making an authenticated call. No device-code request is needed during an update or merely to explain the skill.
4. After successful authorisation, say “账号已连接。上传答卷 PDF 或按页排序的照片，说『帮我批改这份答卷』即可。” If a script was already provided, continue with it instead of asking for another upload. If the user declines or cannot authorise, explain the outcome without claiming connection succeeded.

## Welcome message

**欢迎使用 PassMarkedu A-level 阅卷 Skill，已安装成功。**

基于 [PassMarkedu A-level](<base>) 的真题与官方评分标准服务，帮你逐题批改答卷，并生成三份 PDF：批改答卷、阅卷结果，以及列出 AI 拿不准、需要你来定的几处的复核说明。

**第一步：连接账号**
打开下方授权链接，登录或注册账号，核对授权码后点击「授权」。完成后回到这里，我会自动继续；以后通常无需重复登录。

[登录并授权](<verification_uri_complete>) · 授权码：`<user_code>`

**第二步：上传答卷**
上传 PDF 或按页排序的照片，说「帮我批改这份答卷」。支持整份真题和真题拼题卷，批改答卷保留原卷，使用红色标注分数与得分点；阅卷结果单独提供逐题得分、主要失分点、错误说明、正确解法及官方评分标准。

**支持范围**
- **Edexcel IAL**：数学、进阶数学、物理、化学、经济、会计、生物。
- **CAIE AS & A Level**：数学、进阶数学、物理、化学、经济、会计、计算机科学。

仅支持已收录并开放批改的官方真题及配套评分标准，具体年份与覆盖范围见[常见问题](<base>/marking-kit#faq)。

免费账号可批 1 份整卷和 5 道单题（拍照或拼题卷按题计），订阅后不限次。对判分有异议，可以直接在对话中提出并重新生成结果。
