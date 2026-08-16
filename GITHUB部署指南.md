# GitHub 免费自动部署指南

> 用这个方案之后：**你自己的电脑可以随时关机**。
> 每天北京时间 8:00，GitHub 自己的服务器自动帮你抓新闻+生成页面+发布，手机随时随地打开网址就能看。

---

## 第 0 步 · 先准备

| 项目 | 是什么 | 链接 |
|---|---|---|
| GitHub 账号 | ⭐ 必须要有一个，免费注册 | https://github.com/signup |
| Git 客户端 | 用来把代码推到 GitHub | Windows 下装 Git for Windows https://git-scm.com/download/win |

> 如果装完 Git 第一次用，记得在 cmd/PowerShell 里跑一下（用你 GitHub 注册的名字和邮箱）：
> ```
> git config --global user.name "你的用户名"
> git config --global user.email "你的邮箱@xxx.com"
> ```

---

## 第 1 步 · 在 GitHub 新建一个空仓库

1. 打开 https://github.com/new
2. **Repository name** 随便填，例如 `creator-news`（最好是英文+下划线/数字，不能中文）
3. **Public** 选 Public（公开仓库 Actions/Pages 都完全免费无限量）
4. **不要勾选** `Add a README file` / `Add .gitignore`，保持空仓库
5. 点 **Create repository**

创建成功后会跳到你的空仓库页，**把浏览器地址栏那个链接复制下来**，例如：
```
https://github.com/你的用户名/creator-news.git
```

---

## 第 2 步 · 把本地文件夹推到 GitHub 仓库

### 方法 A（最稳，推荐）

打开 cmd 或 PowerShell，cd 进入当前工作目录：
```
cd  "C:\Users\Administrator\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a8076733013472a35d3508e"
```

然后按顺序执行（把下面的 `你的仓库地址.git` 改成你第1步复制的地址）：

```
git init
git add .
git commit -m "init: 首次提交 工作台+抓取脚本"
git branch -M main
git remote add origin 你的仓库地址.git
git push -u origin main
```

> 推送时会弹出登录 GitHub，选"浏览器登录"最省心，点一下授权就过了。

---

## 第 3 步 · 打开 GitHub Pages（手机能看的网址就有了）

1. 打开你刚建好的仓库页面 → 点顶部 **Settings**（设置）
2. 左侧菜单找到 **Pages**
3. **Source** 那一块默认是 Deploy from a branch，改成：
   - **Source**  → 选 **GitHub Actions**（下拉框）
4. 保存（没保存按钮就自动生效了）

---

## 第 4 步 · 手动触发第一次，看能不能跑通

1. 仓库页面顶部点 **Actions** 标签
2. 左侧列表里选 **「每日资讯自动抓取+发布」**
3. 右上边有个 **Run workflow** 蓝色按钮 → 点一下 → 保持默认参数 → 再点绿色 Run workflow
4. 等 3-5 分钟，刷新页面看状态：
   - ✅ 绿色勾 = 成功
   - ❌ 红色叉 = 失败，点进去看日志截图发我我帮你调

成功之后的部署地址（Pages URL）有两种查看方式：
- 方法①：Settings → Pages，页面中间会显示 `Your site is live at https://xxx.github.io/creator-news/`
- 方法②：Actions → 点开那一次成功的 Run → 拉到最下面 `deploy` job → logs → `pages-url: ...`

**把这个网址发到手机微信/收藏夹，以后天天打开它就行。** 不用管电脑了。

---

## 接下来每天自动跑

- **北京时间每天 8:00 整** 自动触发，抓当天的新闻
- 当天如果 GitHub 服务器抽风没抓到，会自动往前补 7 天（也就是第二天一跑就把昨天空的补上了）
- 想手动立刻抓一次：Actions → 对应 Workflow → Run workflow，想补抓几天就把 `sync_days` 改成多少

---

## 你每天能看到什么？

打开 `https://你的用户名.github.io/你的仓库名/`，会自动跳到新闻列表页：
- 顶部自动重定向到 `news_pages/index.html`（所有日期的新闻列表）
- 想进工作台首页（任务/打卡/选题库）：链接栏末尾加 `workbench-mobile.html`
- 每篇新闻点进去就是标题+摘要+原文链接，三大分类用顶部 Tab 切换

```
┌─────────────────────────────────────┐
│  📰 每日资讯汇总（列表页）            │
│  ┌───────────────────────┐         │
│  │ 08月16日  周日  24条 › │  ← 点进 │
│  ├───────────────────────┤         │
│  │ 08月15日  周六  20条 › │         │
│  └───────────────────────┘         │
└─────────────────────────────────────┘

      ↓ 点 08月16日 进去

┌─────────────────────────────────────┐
│  📰 每日资讯 2026年08月16日 周日     │
│  [🎮梦幻8] [🤖AI8] [🌺兰花8]  ← Tab │
│  ┌───────────────────────┐         │
│  │ 01  梦幻官网公告标题   │         │
│  │     摘要摘要... 官网  │         │
│  ├───────────────────────┤         │
│  │ 02  ...               │         │
│  └───────────────────────┘         │
└─────────────────────────────────────┘
```

---

## 常见问题

**Q：为什么我本地抓梦幻官网能抓到，GitHub上抓不到？**
A：网易有时会屏蔽海外机房 IP（GitHub Actions 服务器在国外），如果哪天猫幻少于8条是正常的；AI和兰花国外源反而比国内抓得还稳。想梦幻100%满8条的话得换方案B（腾讯云/阿里云国内函数）。

**Q：抓下来的历史数据永久保存吗？**
A：是，每次 Actions 会把抓到的 JSON+HTML 作为 commit 推回仓库，Git 永久记录，一年 365 天 365 个文件都在，想查哪天查哪天。

**Q：我把仓库删了怎么办？**
A：那就没了，别删仓库就行。建议设 Private 也可以（Private 仓库每月 Actions 免费 2000 分钟，抓一天才 1-3 分钟，完全够用）。

**Q：想换别的新闻源怎么办？**
A：改本地 `news_fetcher.py` 里 `SOURCES = [...]` 那一段 → 保存 → git push 到仓库，下一次自动跑就用新源了。
