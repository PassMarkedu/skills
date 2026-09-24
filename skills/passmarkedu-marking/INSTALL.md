# 安装 PassMarkEdu 阅卷 Skill

这个文件夹（`passmarkedu-marking/`）就是完整的 Skill，不需要安装任何程序。第一次使用时 Skill 会给出授权链接，在浏览器登录 PassMarkEdu（没有账号先注册）后点「授权」。免费账号可批 1 份试卷，订阅后不限次。使用说明：https://passmarkedu.com/marking-kit

## 三种安装方式（任选其一）

**1. 腾讯 WorkBuddy：SkillHub 一键安装**
在 WorkBuddy 的 SkillHub 搜索「PassMarkEdu 阅卷」，点安装。电脑版和 iPad / 手机 App 都可以用。

**2. 复制一句话给你的 AI（国内网络可用，推荐）**
把下面这句话发给 Codex、Claude、WorkBuddy 或其他支持 Skill 的 AI：

> 请帮我安装 PassMarkEdu 阅卷 Skill：从 https://passmarkedu.com/skills/passmarkedu-marking.zip 下载，解压后把 passmarkedu-marking 文件夹放到你的 Skill 目录（Codex：~/.agents/skills/；Claude Code：~/.claude/skills/；WorkBuddy：~/.workbuddy/skills/），然后告诉我是否安装成功。

网页版 Claude / ChatGPT 不能写本地文件夹：下载上面的 zip，在「设置 → Skills」里上传。

**3. 命令行（需要能访问 GitHub 和 Node.js）**

```
npx skills@latest add PassMarkedu/skills
```

## 用之前

- Codex App：把对话切到「完全访问 / Full access」，否则连不上 PassMarkEdu。
- 建议使用能力较强、能看图的模型；能力较弱的模型可能判错，首页会提示「可信度低」。

## 使用

上传学生答卷扫描件（PDF 或按页顺序的照片），说「帮我批改这份试卷」。结果是一份批改 PDF：首页总分与官方等级，每页答卷旁标分，每页后附逐分点批改说明和官方评分标准。对结果有异议时直接说「6(b) 应该给 1 分，因为……」，Skill 会重新生成，不再占用次数。
