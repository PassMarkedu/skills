# PassMarkedu Skills

AI 阅卷 Skill：按 Cambridge International（CAIE）与 Pearson Edexcel IAL 官方评分标准逐分点批改学生答卷，输出批改 PDF（逐小问标分、批改说明、官方评分标准、官方等级）。评分标准、题目识别、算分与出 PDF 由 [PassMarkedu](https://passmarkedu.com) 服务端完成；使用需要 PassMarkedu 账号（免费 1 份，订阅不限次）。

An AI marking skill for CAIE and Pearson Edexcel IAL past-paper scripts: point-by-point marking against the official mark scheme, returning a marked PDF with the official grade. Requires a PassMarkedu account.

## 安装 / Install

```bash
npx skills@latest add PassMarkedu/skills
```

国内网络推荐：把这句话发给你的 AI（Codex / Claude / WorkBuddy）——

> 请帮我安装 PassMarkedu 阅卷 Skill：从 https://passmarkedu.com/skills/passmarkedu-marking.zip 下载，解压后把 passmarkedu-marking 文件夹放到你的 Skill 目录（Codex：~/.agents/skills/；Claude Code：~/.claude/skills/；WorkBuddy：~/.workbuddy/skills/），然后告诉我是否安装成功。

WorkBuddy 用户也可以在 SkillHub 搜索「PassMarkedu 阅卷」一键安装。

## 使用 / Usage

上传学生答卷扫描件，说「帮我批改这份试卷」。详见 [`skills/passmarkedu-marking/INSTALL.md`](skills/passmarkedu-marking/INSTALL.md) 与 https://passmarkedu.com/marking-kit 。

---

This repository is published from PassMarkedu's main repository; please open issues here or contact support via passmarkedu.com. © PassMark. All rights reserved.
