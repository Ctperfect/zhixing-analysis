<h1 align="center">知行问题分析</h1>

<p align="center"><strong>有目标却卡住了，找一个现在做得到的下一步。</strong></p>

![从理解到实践，再用反馈修正认识](assets/readme-banner.svg)

`zhixing-analysis` 面向已经在用 Codex 推进学习或个人项目的人。你可以带着上次没做到的事回来。助手会沿用已有目标，处理这次具体卡住的地方，根据实际结果调整。

| 你现在需要 | 会话会怎样展开 |
|---|---|
| 只聊聊、休息一下或问清一个概念 | 给短答，按你的要求收束 |
| 想立刻做一点 | 给一个做得到的动作和完成信号 |
| 上次中断了 | 沿用有效安排，处理当时的阻力，选择重启或暂停 |
| 要深挖取舍或安排长期项目 | 比较依据、容量和依赖，按需要展开 |

## 在 Codex 开始

此版的技能发现与调用通过 **Windows 上的 Codex CLI** 实测。Codex 桌面可从技能选择器加载本地技能。其他宿主请按各自的技能导入说明操作，兼容性记录在 [验证报告](evals/REPORT.md)。

在 PowerShell 中将仓库放到 Codex 的个人技能目录。安装位置已经存在时，保留现有文件，按其原有安装方式更新。

```powershell
git clone https://github.com/Ctperfect/zhixing-analysis.git "$env:USERPROFILE\.agents\skills\zhixing-analysis"
```

通过 Git 安装且本地文件无需保留改动时，可用 `git -C "$env:USERPROFILE\.agents\skills\zhixing-analysis" pull --ff-only` 更新。安装规则见 [Codex 官方文档](https://learn.chatgpt.com/docs/build-skills)。

在技能选择器里找 **知行问题分析**，或输入下面的请求。命令行可用 `codex exec --json --skip-git-repo-check '使用 $zhixing-analysis，只用一句话区分最小行动和最小验证。'` 检查，响应事件中的入口读取或技能加载信息可以核对实际使用的路径。技能未显示时检查安装位置，必要时重启 Codex。

```text
使用 $zhixing-analysis。我有学习计划，但下班后总想刷手机。
我今天想继续，只给我一个能开始的动作。
```

## 试一次，再带结果回来

以下是一个虚构的完整会话。实际回复会根据你当下的需要调整。

1. **开始。** 你说「我想写公众号，只有十分钟。」助手建议打开旧稿，写下一个读者问题。写下一句就可以停。
2. **尝试。** 你准备写，结果打开手机就被视频吸引了。你回来报告实际经过。
3. **中断。** 你说「今晚真的累，想休息。」助手接住这个选择，把本轮停在休息。
4. **重启。** 第二天你说「现在想做一点，只剩五分钟。」助手沿用写稿目标，建议把手机留在原处，在电脑稿件写一个问题。你说「写好了，但范围太大」，下一轮就改为缩小这个问题。

这一例可以完全在聊天里完成。带回「做了什么、卡在哪」就能继续。完整对话见 [重启案例](references/cases/restart.md)。

## 保存由你选择

首次保存前，助手会说明位置、可能的可见对象和拟保存的信息，等你确认再写。私人话题可以选择自己控制的位置，避免将个人记录放入公司项目、共享盘、Git 或云同步目录。仅需下一步、约束和反馈时，可以只保存这些摘要。仓库自身的 `.gitignore` 只作用于本仓库。

- 要保存时可以说「把目标、当前容量和下一步保存到我指定的私人目录，省略身份和家庭细节。」随后确认具体位置和可见性。
- 要续接或查看时指定文件，例如「只读取这份记录，沿用仍有效的决定。」
- 要修改或删除时指定文件和范围。已同步或进入 Git 历史的副本有各自的处理范围。

详见 [记录与隐私规则](references/records.md)。

## 方法与评测

方法保留第一性原理、MVP 和反馈校准。深度规划可以同时给出整体阶段和近期每日任务，读取当前容量和依赖，再按用户选择展开。计划形成、动作完成、判断得到支持和目标达成分别依据实际结果。见 [完整方法](references/methodology.md) 和 [规划规则](references/planning.md)。

评测使用合成情境，在相同模型与工具设置下比较有无 Skill 的回答和文件行为。查看 [对照结果与复现步骤](evals/REPORT.md)。

## 许可

仓库当前未发布开放许可。若权利人希望授权复制、修改和分发，MIT 是可供确认的选项，要求保留版权与许可声明。许可现状与选项见 [GitHub 许可说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) 和 [OSI 的 MIT 文本](https://opensource.org/license/mit)。
