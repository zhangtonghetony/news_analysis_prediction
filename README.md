# ⚡ 地缘政治与金融分析系统 (Geopolitical & Financial Analysis System)

这是一个基于大语言模型（LLM）的实时地缘政治与金融风险分析系统。系统通过分析以国际新闻为主的各种文本，动态抽取关键实体（国家、组织、人物、军事力量、金融资产等）及其深层关联，并在前端提供**交互式知识图谱拓扑网**与**多状态混合事件时间轴**的双重可视化呈现。

This is a real-time geopolitical and financial risk analysis system powered by Large Language Models (LLMs). By analyzing diverse text sources, primarily international news, the system dynamically extracts key entities (such as countries, organizations, individuals, military forces, and financial assets) and their deep interconnections. It then provides a dual-visualized presentation on the frontend, featuring an interactive knowledge graph topology network and a multi-state hybrid event timeline.

---

## ✨ 核心特性

* **智能文本解析 (LLM-Driven)**：利用大模型对碎片化的地缘政治、军事或金融分析文本进行深度语义抽取。
* **动态本体（ontology）**:使用爬虫实时抓取新闻，实现本体动态更新；同时加入完善的顶点查重、融合流程。
* **交互式拓扑网络图 (vis-network)**：动态回显实体间的复杂网状关系，支持节点平移、缩放、高亮聚焦及边连线的交互。
* **多状态混合时间轴 (容错与渐进式设计)**：
    * 针对地缘政治或金融暗流中**“发生时间暂不明确（Unknown）”**的边关系，系统引入了**“优雅降级”的分栏机制**。
    * 确切历史节点按时间流升序排列，未知时间的事实单独开辟`⏳ 发生时间待定关联事件`桶进行背景补充，确保数据积累期系统依然高饱满度、高可用。
* **全链条点击联动**：无论在拓扑图中点击节点/连线，还是在时间轴上点击未知时间的事件，系统均能精准联动，自动定位图谱核心并弹出侧边抽屉（Drawer）展示详细的事实线索、可信得分和背景描述。

✨ Core Features
LLM-Driven Intelligent Text Analysis: Leverages large language models to perform deep semantic extraction on fragmented geopolitical, military, or financial analysis texts.

Dynamic Ontology: Utilizes web crawlers to fetch news in real time, enabling dynamic updates to the ontology; it also incorporates a robust pipeline for entity deduplication and fusion.

Interactive Topology Network Graph (vis-network): Dynamically renders complex web-like relationships between entities, supporting interactive features such as node panning, zooming, highlight focusing, and edge/link interactions.

Multi-State Hybrid Timeline (Fault-Tolerant & Progressive Design): Addresses the challenge of relationship edges where the "occurrence time is not yet clear (Unknown)" in geopolitical or financial undercurrents by introducing a "graceful degradation" compartmentalization mechanism.

Definitive historical milestones are sorted in ascending chronological order, while facts with unknown times are funneled into a dedicated ⏳ Pending Time Associated Events bucket as background context. This ensures the system remains data-rich and highly usable during the data accumulation phase.

Full-Chain Click Linkage: Whether clicking a node/edge in the topology graph or an unknown-time event on the timeline, the system achieves precise synchronization—automatically re-centering and focusing on the core of the graph while popping up a side drawer to display detailed factual clues, confidence scores, and background descriptions.

---

## 🖥️ 页面布局与视觉

系统采用经典的**分栏式监控大屏**布局：
1.  **左侧上方**：输入查询区（支持 `Ctrl + Enter` 快速提交）。
2.  **左侧下方**：可视化复合区（左侧为 `vis-network` 拓扑图，右侧为混合时间轴）。
3.  **右侧全高**：基于 `marked` 库流式渲染（Streaming）的 Markdown 格式大模型深度分析报告。

---

## 🛠️ 技术栈

* **前端核心**：Vanilla JS (原生 JavaScript), HTML5, CSS3
* **可视化引擎**：[vis-network](https://github.com/visjs/vis-network) (高性能拓扑图渲染)
* **Markdown 解析**：[marked](https://github.com/markedjs/marked)
* **通信协议**：Server-Sent Events (SSE) / Chunked Stream 流式数据传输
* **后端开发**:Python Flask
* **图数据库**:HugeGraph（免费开源，对大数据量优化完善）

---


<img width="1825" height="857" alt="1e0ba8342b0d3432f24de34cf7336a2d" src="https://github.com/user-attachments/assets/cf7631f7-703d-418d-90cb-f682dc13e49f" />
