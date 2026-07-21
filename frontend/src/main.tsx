import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  BookOpen,
  CheckSquare,
  ExternalLink,
  FileSearch,
  FolderOpen,
  GitBranch,
  LayoutGrid,
  Library,
  List,
  Pause,
  Play,
  RefreshCw,
  Search,
  Send,
  Settings,
  Trash2,
  X
} from "lucide-react";
import "./styles.css";

type ImportResponse = {
  job_id?: string | null;
  status: string;
  duplicate: boolean;
  arxiv_id: string;
  existing_slug?: string;
  existing_report_path?: string;
  message?: string;
};

type Job = {
  id: string;
  type?: string;
  status: string;
  current_step: string;
  progress: number;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  logs?: string[];
  error_message?: string;
  created_at?: string;
  updated_at?: string;
  finished_at?: string;
};

type Paper = {
  slug: string;
  arxiv_id?: string;
  title: string;
  title_zh?: string;
  year?: number;
  status: string;
  reading_stage: string;
  review_stage?: string;
  last_reviewed?: string;
  next_review?: string;
  research_line?: string;
  line_role?: string;
  importance?: number;
  has_code?: number;
  code_url?: string;
  report_html_path?: string;
  report_md_path?: string;
  source_path?: string;
  arxiv_url?: string;
  pdf_url?: string;
  abstract?: string;
  authors?: string[];
  snippet?: string;
  score?: number;
  matched_chunk?: string;
  tags?: Record<string, string[]>;
};

type AppSettings = {
  llm_provider: string;
  llm_model: string;
  openai_base_url: string;
  openai_api_key_set: boolean;
  embedding_enabled: boolean;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimension: number;
  report_dir: string;
  source_dir: string;
  db_path: string;
  active_api_profile_id: string;
};

type ApiProfile = {
  id: string;
  name: string;
  llm_provider: string;
  llm_model: string;
  openai_base_url: string;
  api_key_set: boolean;
  is_active: boolean;
};

type LLMTestResponse = {
  ok: boolean;
  message: string;
  provider: string;
  model: string;
};

type ApiProfileTestResult = {
  status: "testing" | "success" | "error";
  message: string;
  detail?: string;
};

type ApiProfilesPayload = {
  settings?: AppSettings;
  items: ApiProfile[];
};

type ResearchLine = {
  name: string;
  count: number;
  roles: Record<string, Paper[]>;
};

type ViewKey = "import" | "library" | "settings";
type LibraryLayout = "list" | "cards";
type DirectoryTarget = "source" | "report";

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function statusText(value?: string) {
  const labels: Record<string, string> = {
    queued: "准备开始",
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    paused: "已暂停",
    canceled: "已取消",
    needs_llm: "等待模型配置",
    duplicate: "已存在",
    unread: "未读",
    reading: "阅读中",
    read: "已读",
    archived: "已归档"
  };
  return value ? labels[value] || value : "未知";
}

function stepText(value?: string) {
  const labels: Record<string, string> = {
    queued: "准备开始",
    fetching_metadata: "获取论文元数据",
    downloading_source: "下载源码",
    extracting_source: "解压源码",
    detecting_code: "检测代码仓库",
    needs_llm_report_generation: "等待模型生成报告",
    generating_report: "生成阅读报告",
    rendering_html: "渲染 HTML",
    rebuilding_wiki: "刷新 Wiki",
    completed: "已完成",
    failed: "失败",
    canceled: "已取消",
    invalid_input: "输入无效"
  };
  return value ? labels[value] || value : "准备开始";
}

function stageText(value?: string) {
  const labels: Record<string, string> = {
    skim: "粗读",
    deep_read: "深读",
    code_checked: "代码已检查",
    fresh: "新加入",
    second_pass: "二刷",
    queued: "排队中"
  };
  return value ? labels[value] || value : "未设置";
}

function summarizeApiFeedback(message: string) {
  const firstLine = message.split(/\r?\n/).find((line) => line.trim());
  if (!firstLine) return "";
  return firstLine.length > 150 ? `${firstLine.slice(0, 150)}...` : firstLine;
}

function paperTitle(paper: Paper) {
  return paper.title_zh || paper.title || paper.slug;
}

function compactTags(paper: Paper, type: string, limit = 3) {
  return paper.tags?.[type]?.slice(0, limit) || [];
}

function textValue(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function jobPaperTitle(job: Job) {
  return (
    textValue(job.output?.title_zh) ||
    textValue(job.output?.title) ||
    textValue(job.output?.slug) ||
    textValue(job.input?.arxiv_id) ||
    "当前论文"
  );
}

function jobPaperMeta(job: Job) {
  return (
    textValue(job.output?.slug) ||
    textValue(job.input?.arxiv_id) ||
    ""
  );
}

function joinDistinctTitleMeta(title: string, meta: string) {
  if (!meta || title === meta) return title;
  return `${title} · ${meta}`;
}

function formatJobLog(log: string) {
  const message = log.replace(/^\d{4}-\d{2}-\d{2}T\S+\s+/, "");
  if (message === "job queued") return "已开始准备分析";
  if (message === "analysis paused by user") return "已暂停，等待继续";
  if (message === "analysis resumed") return "已继续分析";
  if (message === "analysis canceled by user") return "已取消，可以修改链接后重新开始";
  if (message.includes("marked complete")) return "完成入库并生成阅读报告";
  if (message.startsWith("fetching arXiv metadata")) return "正在读取 arXiv 元数据";
  if (message.startsWith("metadata fetched")) return "元数据已获取，准备下载源码";
  if (message.startsWith("downloaded e-print")) return "源码包已下载完成";
  if (message.startsWith("scanning paper source")) return "正在检查论文源码与代码链接";
  if (message.startsWith("starting deep paper analysis")) return "正在启动深度论文分析";
  if (message.includes("整理阅读札记")) return "正在精读源码并整理阅读札记";
  if (message.includes("批判性分析备忘录")) return "正在核对相关工作与局限";
  if (message.includes("正式中文深度阅读报告")) return "正在生成正式深度阅读报告";
  if (message.includes("质量规则修订报告")) return "正在按质量规则修订报告";
  if (message.startsWith("generating report")) return "正在调用 AI 生成中文阅读报告";
  if (message.startsWith("report written")) return "Markdown 报告已写入本地";
  if (message.startsWith("HTML rendered")) return "HTML 阅读报告已渲染完成";
  if (message.startsWith("paper import pipeline completed")) return "文献已同步到本地知识库";
  if (message.startsWith("waiting for LLM configuration")) return "等待补充 AI 模型配置";
  if (message.startsWith("failed")) return "任务失败，请查看错误信息";
  return message;
}

function parseTimestamp(value?: string) {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatDuration(ms: number) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function jobElapsed(job: Job, now: number) {
  const startedAt = parseTimestamp(job.created_at);
  if (!startedAt) return "";
  const endedAt = parseTimestamp(job.finished_at) || (["completed", "failed"].includes(job.status) ? parseTimestamp(job.updated_at) : now);
  return formatDuration(endedAt - startedAt);
}

const ALL_RESEARCH_LINES = "__all__";
const UNASSIGNED_RESEARCH_LINE = "__unassigned__";
const IMPORT_STEPS = [
  ["fetching_metadata", "元数据"],
  ["downloading_source", "源码"],
  ["extracting_source", "解析"],
  ["detecting_code", "代码"],
  ["generating_report", "AI 分析"],
  ["rendering_html", "报告"],
  ["rebuilding_wiki", "入库"]
];

function importStepIndex(currentStep?: string) {
  if (currentStep === "completed") return IMPORT_STEPS.length;
  const aliases: Record<string, string> = {
    queued: "fetching_metadata",
    needs_llm_report_generation: "generating_report"
  };
  const normalized = currentStep ? aliases[currentStep] || currentStep : "";
  return IMPORT_STEPS.findIndex(([step]) => step === normalized);
}

const views: Array<{ key: ViewKey; label: string; title: string; icon: React.ReactNode }> = [
  { key: "import", label: "导入", title: "导入 arXiv 论文", icon: <Send size={18} /> },
  { key: "library", label: "文献库", title: "文献库", icon: <Library size={18} /> },
  { key: "settings", label: "设置", title: "设置", icon: <Settings size={18} /> }
];

function App() {
  const [activeView, setActiveView] = useState<ViewKey>("library");
  const [url, setUrl] = useState("");
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-4.1");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [embeddingProvider, setEmbeddingProvider] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("hashing-v1");
  const [embeddingDimension, setEmbeddingDimension] = useState("64");
  const [reportDir, setReportDir] = useState("");
  const [sourceDir, setSourceDir] = useState("");
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [apiTestStatus, setApiTestStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [apiTestMessage, setApiTestMessage] = useState("");
  const [apiTestDetail, setApiTestDetail] = useState("");
  const [showApiTestDetail, setShowApiTestDetail] = useState(false);
  const [apiProfiles, setApiProfiles] = useState<ApiProfile[]>([]);
  const [apiProfileTests, setApiProfileTests] = useState<Record<string, ApiProfileTestResult>>({});
  const [profileName, setProfileName] = useState("");
  const [editingApiProfileId, setEditingApiProfileId] = useState("");
  const [editingProfileName, setEditingProfileName] = useState("");
  const [claudeProfiles, setClaudeProfiles] = useState<Array<{id: string; name: string; model: string; base_url: string}>>([]);
  const [selectedClaudeProfile, setSelectedClaudeProfile] = useState("");
  const [editingProfileModel, setEditingProfileModel] = useState("");
  const [editingProfileBaseUrl, setEditingProfileBaseUrl] = useState("");
  const [editingProfileApiKey, setEditingProfileApiKey] = useState("");
  const [force, setForce] = useState(false);
  const [importResult, setImportResult] = useState<ImportResponse | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [researchLines, setResearchLines] = useState<ResearchLine[]>([]);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [reportPaper, setReportPaper] = useState<Paper | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchKind, setSearchKind] = useState<"keyword" | "semantic">("keyword");
  const [semanticNotice, setSemanticNotice] = useState("");
  const [searchMode, setSearchMode] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [importanceFilter, setImportanceFilter] = useState("");
  const [codeFilter, setCodeFilter] = useState("");
  const [selectedResearchLine, setSelectedResearchLine] = useState(ALL_RESEARCH_LINES);
  const [libraryLayout, setLibraryLayout] = useState<LibraryLayout>("list");
  const [bulkEditMode, setBulkEditMode] = useState(false);
  const [selectedSlugs, setSelectedSlugs] = useState<string[]>([]);
  const [bulkResearchLine, setBulkResearchLine] = useState("");
  const [pickingDirectory, setPickingDirectory] = useState<DirectoryTarget | "">("");
  const [libraryNotice, setLibraryNotice] = useState("");
  const [topicFilter, setTopicFilter] = useState("");
  const [methodFilter, setMethodFilter] = useState("");
  const [classificationLine, setClassificationLine] = useState("");
  const [classificationRole, setClassificationRole] = useState("");
  const [classificationTopics, setClassificationTopics] = useState("");
  const [classificationMethods, setClassificationMethods] = useState("");
  const [classificationNotice, setClassificationNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [nowTick, setNowTick] = useState(() => Date.now());

  const queuedJobIds = useMemo(
    () => jobs
      .filter((job) => ["queued", "running", "needs_llm"].includes(job.status))
      .map((job) => job.id)
      .filter(Boolean),
    [jobs]
  );

  const importJobs = useMemo(
    () => jobs
      .filter((job) => job.type === "paper_import")
      .sort((a, b) => parseTimestamp(a.created_at) - parseTimestamp(b.created_at)),
    [jobs]
  );

  const activeImportJob = useMemo(() => {
    const live = importJobs.find((job) => ["running", "needs_llm", "paused"].includes(job.status));
    if (live) return live;
    return importJobs.find((job) => job.status === "queued") || jobs[0] || null;
  }, [importJobs, jobs]);
  const queuedImportJobs = useMemo(
    () => importJobs.filter((job) => job.status === "queued" && job.id !== activeImportJob?.id),
    [activeImportJob, importJobs]
  );
  const paperBySlug = useMemo(
    () => new Map(papers.map((paper) => [paper.slug, paper])),
    [papers]
  );
  const paperForJob = (job?: Job | null) => {
    const slug = textValue(job?.output?.slug);
    return slug ? paperBySlug.get(slug) || null : null;
  };
  const activeImportPaper = paperForJob(activeImportJob);
  const isImportJobLive = Boolean(activeImportJob && ["queued", "running", "needs_llm"].includes(activeImportJob.status));
  const isImportJobPaused = activeImportJob?.status === "paused";
  const hasActiveImportProcess = Boolean(activeImportJob && ["queued", "running", "needs_llm", "paused"].includes(activeImportJob.status));
  const activeImportElapsed = activeImportJob ? jobElapsed(activeImportJob, nowTick) : "";
  const activeImportElapsedLabel = activeImportJob?.status === "completed" || activeImportJob?.status === "failed" || activeImportJob?.status === "canceled" ? "总耗时" : "已用时";
  const activeImportLogs = useMemo(
    () => (activeImportJob?.logs || []).slice(-4).reverse(),
    [activeImportJob]
  );
  const activeImportActivityItems = useMemo(() => {
    const logs = activeImportLogs.map(formatJobLog);
    if (!activeImportJob) return [];
    return logs;
  }, [activeImportJob, activeImportLogs, isImportJobLive]);
  const importPreviewPaper = activeImportPaper || papers.find((paper) => paper.report_html_path) || null;
  const recentCompletedPapers = useMemo(
    () => papers.filter((paper) => paper.report_html_path).slice(0, 3),
    [papers]
  );
  const topbarStats = useMemo(
    () => [
      { label: "当前列表", value: papers.length },
      { label: "领域", value: researchLines.filter((line) => line.name !== "Unassigned").length },
      { label: "未分类", value: papers.filter((paper) => !paper.research_line).length },
      { label: "分析中", value: jobs.filter((job) => ["queued", "running", "needs_llm", "paused"].includes(job.status)).length }
    ],
    [jobs, papers, researchLines]
  );

  const allResearchLineCount = useMemo(
    () => researchLines.reduce((total, line) => total + line.count, 0),
    [researchLines]
  );
  const namedResearchLines = useMemo(
    () => researchLines
      .filter((line) => line.name !== "Unassigned")
      .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name)),
    [researchLines]
  );
  const unassignedResearchLine = researchLines.find((line) => line.name === "Unassigned");
  const unassignedResearchLineCount = unassignedResearchLine?.count || papers.filter((paper) => !paper.research_line).length;
  const selectedPaperRows = useMemo(
    () => papers.filter((paper) => selectedSlugs.includes(paper.slug)),
    [papers, selectedSlugs]
  );
  const allVisibleSelected = papers.length > 0 && papers.every((paper) => selectedSlugs.includes(paper.slug));
  const activeFilterCount = [
    statusFilter,
    importanceFilter,
    codeFilter,
    topicFilter.trim(),
    methodFilter.trim()
  ].filter(Boolean).length;

  function researchLineLabel(name: string) {
    return name === "Unassigned" ? "未分类" : name;
  }

  function toggleSelectedPaper(slug: string) {
    setSelectedSlugs((existing) => (
      existing.includes(slug)
        ? existing.filter((item) => item !== slug)
        : [...existing, slug]
    ));
  }

  function toggleAllVisiblePapers() {
    setSelectedSlugs((existing) => {
      const visibleSlugs = papers.map((paper) => paper.slug);
      if (visibleSlugs.length > 0 && visibleSlugs.every((slug) => existing.includes(slug))) {
        return existing.filter((slug) => !visibleSlugs.includes(slug));
      }
      return Array.from(new Set([...existing, ...visibleSlugs]));
    });
  }

  async function refreshPapers(researchLine = selectedResearchLine) {
    const params = new URLSearchParams({ limit: "500" });
    if (statusFilter) params.set("status", statusFilter);
    if (importanceFilter) params.set("importance", importanceFilter);
    if (codeFilter) params.set("has_code", codeFilter);
    if (researchLine !== ALL_RESEARCH_LINES) params.set("research_line", researchLine);
    if (topicFilter.trim()) params.set("topic", topicFilter.trim());
    if (methodFilter.trim()) params.set("method", methodFilter.trim());
    const payload = await getJson<{ items: Paper[] }>(`/api/papers?${params.toString()}`);
    setPapers(payload.items);
    setSearchMode(false);
    setSemanticNotice("");
  }

  function clearFilters() {
    setStatusFilter("");
    setImportanceFilter("");
    setCodeFilter("");
    setTopicFilter("");
    setMethodFilter("");
  }

  async function chooseResearchLine(researchLine: string) {
    setSelectedResearchLine(researchLine);
    setError("");
    await refreshPapers(researchLine);
  }

  async function chooseDirectory(target: DirectoryTarget) {
    setError("");
    setPickingDirectory(target);
    const currentPath = target === "source" ? sourceDir : reportDir;
    const prompt = target === "source" ? "选择源码目录" : "选择报告目录";
    try {
      const response = await fetch("/api/system/select-directory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_path: currentPath, prompt })
      });
      if (response.status === 409) return;
      if (!response.ok) {
        setError(await response.text());
        return;
      }
      const payload = (await response.json()) as { path?: string };
      if (!payload.path) return;
      if (target === "source") {
        setSourceDir(payload.path);
      } else {
        setReportDir(payload.path);
      }
    } finally {
      setPickingDirectory("");
    }
  }

  async function refreshJobs() {
    const payload = await getJson<{ items: Job[] }>("/api/jobs?limit=20");
    setJobs(payload.items);
  }

  async function refreshResearchLines() {
    const payload = await getJson<{ items: ResearchLine[] }>("/api/research-lines");
    setResearchLines(payload.items);
  }

  async function refreshAll() {
    setError("");
    await Promise.all([
      refreshPapers(),
      refreshJobs(),
      refreshResearchLines(),
      refreshSettings(),
      refreshApiProfiles()
    ]);
  }

  async function selectPaper(slug: string) {
    setError("");
    try {
      const paper = await getJson<Paper>(`/api/papers/${encodeURIComponent(slug)}`);
      setSelectedPaper(paper);
      setClassificationNotice("");
    } catch (caught) {
      setError(String(caught));
    }
  }

  function splitLabels(value: string) {
    return value
      .split(/[,，/]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function saveClassification(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedPaper) return;
    setError("");
    setLibraryNotice("");
    setClassificationNotice("");
    const response = await fetch(`/api/papers/${encodeURIComponent(selectedPaper.slug)}/classification`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        research_line: classificationLine,
        line_role: classificationRole,
        topics: splitLabels(classificationTopics),
        methods: splitLabels(classificationMethods)
      })
    });
    if (!response.ok) {
      setError(await response.text());
      return;
    }
    const paper = (await response.json()) as Paper;
    setSelectedPaper(paper);
    await refreshResearchLines();
    await refreshPapers();
    setClassificationNotice("分类已更新");
  }

  async function applyBulkResearchLine() {
    const line = bulkResearchLine.trim();
    if (!selectedPaperRows.length || !line) return;
    setError("");
    setClassificationNotice("");
    try {
      await Promise.all(selectedPaperRows.map((paper) => fetch(`/api/papers/${encodeURIComponent(paper.slug)}/classification`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          research_line: line,
          line_role: paper.line_role || "",
          topics: paper.tags?.topic || [],
          methods: paper.tags?.method || []
        })
      }).then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
      })));
      setSelectedSlugs([]);
      setBulkResearchLine("");
      setBulkEditMode(false);
      await refreshResearchLines();
      await refreshPapers();
      setLibraryNotice(`已更新 ${selectedPaperRows.length} 篇论文的领域`);
    } catch (caught) {
      setError(String(caught));
    }
  }

  async function deleteSelectedPapers() {
    if (!selectedPaperRows.length) return;
    const names = selectedPaperRows.slice(0, 3).map((paper) => `「${paperTitle(paper)}」`).join("、");
    const extra = selectedPaperRows.length > 3 ? ` 等 ${selectedPaperRows.length} 篇` : "";
    const confirmed = window.confirm(`确定删除 ${names}${extra} 吗？\n\n这会从文献库移除记录，并删除本地 Markdown/HTML 阅读报告文件。`);
    if (!confirmed) return;

    setError("");
    try {
      const results = await Promise.all(selectedPaperRows.map(async (paper) => {
        const response = await fetch(`/api/papers/${encodeURIComponent(paper.slug)}`, { method: "DELETE" });
        if (!response.ok) throw new Error(await response.text());
        return response.json() as Promise<{ slug: string; file_errors?: string[]; wiki_error?: string }>;
      }));
      const fileErrorCount = results.reduce((total, result) => total + (result.file_errors?.length || 0), 0);
      const wikiError = results.find((result) => result.wiki_error)?.wiki_error;
      setSelectedSlugs([]);
      setSelectedPaper(null);
      await Promise.all([refreshPapers(), refreshResearchLines(), refreshJobs()]);
      setLibraryNotice(
        fileErrorCount || wikiError
          ? `已删除 ${results.length} 篇；有 ${fileErrorCount} 个文件未能删除${wikiError ? "，Wiki 刷新需要手动重试" : ""}`
          : `已删除 ${results.length} 篇论文和对应阅读报告`
      );
    } catch (caught) {
      setError(String(caught));
    }
  }

  function fileUrl(path?: string) {
    if (!path) return "";
    return `/api/files?path=${encodeURIComponent(path)}`;
  }

  function openReportInApp(paper: Paper) {
    if (!paper.report_html_path) {
      selectPaper(paper.slug).catch((caught) => setError(String(caught)));
      return;
    }
    setReportPaper(paper);
  }

  function openDetailsFromReport(paper: Paper) {
    setReportPaper(null);
    selectPaper(paper.slug).catch((caught) => setError(String(caught)));
  }

  async function refreshSettings() {
    const payload = await getJson<AppSettings>("/api/settings");
    setSettings(payload);
    const currentProvider = payload.llm_provider || "openai";
    setProvider(currentProvider);
    if (currentProvider === "claude-code") {
      setSelectedClaudeProfile(payload.llm_model || "");
    } else {
      setModel(payload.llm_model || "gpt-4.1");
    }
    setBaseUrl(payload.openai_base_url || "https://api.openai.com/v1");
    setEmbeddingProvider(payload.embedding_provider || "");
    setEmbeddingModel(payload.embedding_model || "hashing-v1");
    setEmbeddingDimension(String(payload.embedding_dimension || 64));
    setReportDir(payload.report_dir || "");
    setSourceDir(payload.source_dir || "");
  }

  async function refreshApiProfiles() {
    const payload = await getJson<{ items: ApiProfile[] }>("/api/settings/api-profiles");
    setApiProfiles(payload.items);
  }

  async function refreshClaudeProfiles() {
    try {
      const payload = await getJson<{ items: Array<{id: string; name: string; model: string; base_url: string}> }>("/api/claude-profiles");
      setClaudeProfiles(payload.items);
      if (payload.items.length > 0 && !selectedClaudeProfile) {
        setSelectedClaudeProfile(payload.items[0].id);
      }
    } catch {
      // Claude profiles not available, that's ok
    }
  }

  async function saveSettings(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    const effectiveModel = provider === "claude-code" ? selectedClaudeProfile : model;
    const response = await fetch("/api/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        llm_provider: provider,
        llm_model: effectiveModel,
        openai_base_url: baseUrl,
        openai_api_key: apiKey.trim() ? apiKey : undefined,
        report_dir: reportDir,
        source_dir: sourceDir,
        embedding_provider: embeddingProvider,
        embedding_model: embeddingModel,
        embedding_dimension: embeddingDimension
      })
    });
    if (!response.ok) {
      setError(await response.text());
      return;
    }
    const payload = (await response.json()) as AppSettings;
    setSettings(payload);
    setApiKey("");
    setApiTestStatus("success");
    setApiTestMessage("✅ 设置已保存");
    setTimeout(() => {
      setApiTestStatus("idle");
      setApiTestMessage("");
    }, 3000);
    await refreshSettings();
    await refreshApiProfiles();
  }

  async function saveCurrentApiProfile() {
    const name = profileName.trim();
    if (!name) {
      setApiTestStatus("error");
      setApiTestMessage("请先给这组 API 配置起一个名称。");
      return;
    }
    setError("");
    const response = await fetch("/api/settings/api-profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        llm_provider: provider,
        llm_model: model,
        openai_base_url: baseUrl,
        openai_api_key: apiKey.trim() ? apiKey : undefined
      })
    });
    if (!response.ok) {
      setApiTestStatus("error");
      setApiTestMessage(await response.text());
      return;
    }
    const payload = (await response.json()) as ApiProfilesPayload;
    if (payload.settings) {
      setSettings(payload.settings);
    }
    setApiProfiles(payload.items);
    setProfileName("");
    setApiTestStatus("success");
    setApiTestMessage("已保存为 API 配置，可在下方启用。");
  }

  function startEditingApiProfile(profile: ApiProfile) {
    setEditingApiProfileId(profile.id);
    setEditingProfileName(profile.name);
    setEditingProfileModel(profile.llm_model);
    setEditingProfileBaseUrl(profile.openai_base_url);
    setEditingProfileApiKey("");
    setApiProfileTests((existing) => {
      const next = { ...existing };
      delete next[profile.id];
      return next;
    });
  }

  function cancelEditingApiProfile() {
    setEditingApiProfileId("");
    setEditingProfileName("");
    setEditingProfileModel("");
    setEditingProfileBaseUrl("");
    setEditingProfileApiKey("");
  }

  async function saveEditedApiProfile(profile: ApiProfile) {
    const name = editingProfileName.trim();
    const nextModel = editingProfileModel.trim();
    const nextBaseUrl = editingProfileBaseUrl.trim();
    if (!name || !nextModel || !nextBaseUrl) {
      setApiProfileTests((existing) => ({
        ...existing,
        [profile.id]: { status: "error", message: "名称、模型和接口地址不能为空。" }
      }));
      return;
    }
    setError("");
    const response = await fetch("/api/settings/api-profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: profile.id,
        name,
        llm_provider: profile.llm_provider || "openai",
        llm_model: nextModel,
        openai_base_url: nextBaseUrl,
        openai_api_key: editingProfileApiKey.trim() ? editingProfileApiKey : undefined
      })
    });
    if (!response.ok) {
      const detail = await response.text();
      setApiProfileTests((existing) => ({
        ...existing,
        [profile.id]: { status: "error", message: summarizeApiFeedback(detail), detail }
      }));
      return;
    }
    const payload = (await response.json()) as ApiProfilesPayload;
    if (payload.settings) {
      setSettings(payload.settings);
      if (profile.is_active) {
        setProvider(payload.settings.llm_provider || "openai");
        setModel(payload.settings.llm_model || "gpt-4.1");
        setBaseUrl(payload.settings.openai_base_url || "https://api.openai.com/v1");
        setApiKey("");
      }
    }
    setApiProfiles(payload.items);
    setApiProfileTests((existing) => ({
      ...existing,
      [profile.id]: { status: "success", message: "配置已更新，可重新测试连接。" }
    }));
    cancelEditingApiProfile();
  }

  async function toggleApiProfile(profile: ApiProfile) {
    setError("");
    const action = profile.is_active ? "deactivate" : "activate";
    const response = await fetch(`/api/settings/api-profiles/${encodeURIComponent(profile.id)}/${action}`, { method: "POST" });
    if (!response.ok) {
      setApiTestStatus("error");
      setApiTestMessage(await response.text());
      return;
    }
    const payload = (await response.json()) as { settings: AppSettings; items: ApiProfile[] };
    setSettings(payload.settings);
    setProvider(payload.settings.llm_provider || "openai");
    setModel(payload.settings.llm_model || "gpt-4.1");
    setBaseUrl(payload.settings.openai_base_url || "https://api.openai.com/v1");
    setApiKey("");
    setApiProfiles(payload.items);
    setApiTestStatus("success");
    setApiTestMessage(profile.is_active ? "已取消启用该 API 配置。" : "已启用选中的 API 配置。");
  }

  async function deleteApiProfile(profileId: string) {
    setError("");
    const response = await fetch(`/api/settings/api-profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
    if (!response.ok) {
      setApiTestStatus("error");
      setApiTestMessage(await response.text());
      return;
    }
    const payload = (await response.json()) as { items: ApiProfile[] };
    setApiProfiles(payload.items);
    setApiProfileTests((existing) => {
      const next = { ...existing };
      delete next[profileId];
      return next;
    });
  }

  async function testApiProfile(profile: ApiProfile) {
    setError("");
    setApiProfileTests((existing) => ({
      ...existing,
      [profile.id]: { status: "testing", message: "正在测试连接..." }
    }));
    const response = await fetch(`/api/settings/api-profiles/${encodeURIComponent(profile.id)}/test`, { method: "POST" });
    if (!response.ok) {
      const detail = await response.text();
      setApiProfileTests((existing) => ({
        ...existing,
        [profile.id]: { status: "error", message: summarizeApiFeedback(detail), detail }
      }));
      return;
    }
    const payload = (await response.json()) as LLMTestResponse;
    const detail = payload.message || (payload.ok ? "连接成功" : "连接失败");
    setApiProfileTests((existing) => ({
      ...existing,
      [profile.id]: {
        status: payload.ok ? "success" : "error",
        message: payload.ok ? detail : summarizeApiFeedback(detail),
        detail: payload.ok ? "" : detail
      }
    }));
  }

  async function testApiConnection() {
    setError("");
    setApiTestStatus("testing");
    setApiTestMessage("正在测试当前模型配置...");
    setApiTestDetail("");
    setShowApiTestDetail(false);
    const effectiveModel = provider === "claude-code" ? selectedClaudeProfile : model;
    const response = await fetch("/api/settings/test-llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        llm_provider: provider,
        llm_model: effectiveModel,
        openai_base_url: baseUrl,
        openai_api_key: apiKey.trim() ? apiKey : undefined
      })
    });
    if (!response.ok) {
      const detail = await response.text();
      setApiTestStatus("error");
      setApiTestMessage(summarizeApiFeedback(detail));
      setApiTestDetail(detail);
      setShowApiTestDetail(true);
      return;
    }
    const payload = (await response.json()) as LLMTestResponse;
    setApiTestStatus(payload.ok ? "success" : "error");
    const detail = payload.message || (payload.ok ? "连接成功" : "连接失败");
    setApiTestMessage(payload.ok ? detail : summarizeApiFeedback(detail));
    setApiTestDetail(payload.ok ? "" : detail);
    setShowApiTestDetail(!payload.ok);
  }

  async function rebuildSemanticIndex() {
    setError("");
    setSemanticNotice("");
    const response = await fetch("/api/semantic/reindex", { method: "POST" });
    if (!response.ok) {
      setError(await response.text());
      return;
    }
    const payload = await response.json() as { indexed_chunks: number };
    setSemanticNotice(`已索引 ${payload.indexed_chunks} 个片段`);
  }

  async function resumeJob(jobId: string) {
    setError("");
    const response = await fetch(`/api/jobs/${jobId}/run`, { method: "POST" });
    if (!response.ok) {
      setError(await response.text());
      return;
    }
    const payload = (await response.json()) as { job?: Job };
    const job = payload.job || await getJson<Job>(`/api/jobs/${jobId}`);
    setJobs((existing) => existing.map((item) => (item.id === jobId ? job : item)));
  }

  async function pauseJob(jobId: string) {
    setError("");
    const response = await fetch(`/api/jobs/${jobId}/pause`, { method: "POST" });
    if (!response.ok) {
      setError(await response.text());
      return;
    }
    const payload = (await response.json()) as { job?: Job };
    const job = payload.job || await getJson<Job>(`/api/jobs/${jobId}`);
    setJobs((existing) => existing.map((item) => (item.id === jobId ? job : item)));
  }

  async function cancelJob(jobId: string) {
    setError("");
    const response = await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
    if (!response.ok) {
      setError(await response.text());
      return;
    }
    const payload = (await response.json()) as { job?: Job };
    const job = payload.job || await getJson<Job>(`/api/jobs/${jobId}`);
    setJobs((existing) => existing.map((item) => (item.id === jobId ? job : item)));
    if (importResult?.job_id === jobId) {
      setImportResult(null);
    }
  }

  async function searchLibrary(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSemanticNotice("");
    if (!searchQuery.trim()) {
      await refreshPapers();
      return;
    }
    const endpoint = searchKind === "semantic" ? "/api/semantic/search" : "/api/search";
    const payload = await getJson<{ items: Paper[] }>(
      `${endpoint}?q=${encodeURIComponent(searchQuery.trim())}&limit=50`
    );
    const items = selectedResearchLine === ALL_RESEARCH_LINES
      ? payload.items
      : payload.items.filter((paper) => (
        selectedResearchLine === UNASSIGNED_RESEARCH_LINE
          ? !paper.research_line
          : paper.research_line === selectedResearchLine
    ));
    setPapers(items);
    setSearchMode(true);
    if (searchKind === "semantic") {
      setSemanticNotice(`已按语义相似返回 ${items.length} 篇论文`);
    }
  }

  async function submitImport(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const response = await fetch("/api/papers/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          force
        })
      });
      const payload = (await response.json()) as ImportResponse;
      if (!response.ok) {
        throw new Error(JSON.stringify(payload));
      }
      setImportResult(payload);
      if (payload.job_id) {
        const job = await getJson<Job>(`/api/jobs/${payload.job_id}`);
        setJobs((existing) => [job, ...existing.filter((item) => item.id !== job.id)]);
        setUrl("");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshPapers().catch((caught) => setError(String(caught)));
    refreshJobs().catch((caught) => setError(String(caught)));
    refreshResearchLines().catch((caught) => setError(String(caught)));
    refreshSettings().catch((caught) => setError(String(caught)));
    refreshApiProfiles().catch((caught) => setError(String(caught)));
    refreshClaudeProfiles().catch(() => {});
  }, []);

  useEffect(() => {
    if (!queuedJobIds.length) return;
    const timer = window.setInterval(() => {
      Promise.all(queuedJobIds.map((id) => getJson<Job>(`/api/jobs/${id}`)))
        .then((updatedJobs) => {
          setJobs((existingJobs) => {
            const updatedById = new Map(updatedJobs.map((job) => [job.id, job]));
            return existingJobs.map((job) => updatedById.get(job.id) || job);
          });
        })
        .catch((caught) => setError(String(caught)));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [queuedJobIds]);

  useEffect(() => {
    if (!isImportJobLive) return;
    const timer = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isImportJobLive]);

  useEffect(() => {
    function closeDrawer(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (showApiTestDetail) {
          setShowApiTestDetail(false);
        } else if (reportPaper) {
          setReportPaper(null);
        } else {
          setSelectedPaper(null);
        }
      }
    }
    window.addEventListener("keydown", closeDrawer);
    return () => window.removeEventListener("keydown", closeDrawer);
  }, [reportPaper, showApiTestDetail]);

  useEffect(() => {
    if (!selectedPaper) return;
    setClassificationLine(selectedPaper.research_line || "");
    setClassificationRole(selectedPaper.line_role || "");
    setClassificationTopics(selectedPaper.tags?.topic?.join(", ") || "");
    setClassificationMethods(selectedPaper.tags?.method?.join(", ") || "");
  }, [selectedPaper]);

  useEffect(() => {
    const visibleSlugs = new Set(papers.map((paper) => paper.slug));
    setSelectedSlugs((existing) => existing.filter((slug) => visibleSlugs.has(slug)));
  }, [papers]);

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand">
          <BookOpen size={24} />
          <div>
            <strong>AutoPaperReader</strong>
            <span>本地论文知识库</span>
          </div>
        </div>
        <div className="header-actions">
          <div className="topbar-stats header-stats" aria-label="知识库概览">
            {topbarStats.map((stat) => (
              <span key={stat.label}>{stat.label} {stat.value}</span>
            ))}
          </div>
          <button className="icon-button header-refresh" onClick={() => refreshAll().catch((caught) => setError(String(caught)))} title="刷新全部">
            <RefreshCw size={18} />
          </button>
          <nav className="main-nav" aria-label="主导航">
            {views.map((view) => (
              <button
                className={activeView === view.key ? "nav-item active" : "nav-item"}
                key={view.key}
                onClick={() => setActiveView(view.key)}
              >
                {view.icon}
                {view.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <section className="workspace">
        {activeView === "import" && <section id="import" className="panel import-panel">
          <div className="import-workbench">
            <div className="import-composer">
              <div className="panel-heading">
                <FileSearch size={20} />
                <h2>导入 arXiv 论文</h2>
              </div>
              <p className="import-lede">粘贴一篇 arXiv 链接，AutoPaperReader 会自动拉取源码、调用设置里的 AI 模型，并整理成中文阅读报告。</p>
              {settings && (
                <div className="import-current-provider">
                  当前 AI：<strong>{settings.llm_provider === "claude-code" ? "Claude Code" : "OpenAI 兼容"}</strong>
                  {settings.llm_provider === "claude-code" ? (
                    <span> · Profile: {settings.llm_model || "未选择"}</span>
                  ) : (
                    <span> · 模型: {settings.llm_model || "未设置"}</span>
                  )}
                  <button className="small-button ghost-button" type="button" onClick={() => setActiveView("settings")}>更换</button>
                </div>
              )}
              <form onSubmit={submitImport} className="import-form">
                <label>
                  arXiv 链接
                  <input
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    placeholder="https://arxiv.org/abs/1706.03762"
                  />
                </label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={force}
                    onChange={(event) => setForce(event.target.checked)}
                  />
                  强制重新导入
                </label>
                <button className="primary-button import-submit" disabled={loading || !url.trim()}>
                  <Send size={17} />
                  {loading ? "提交中" : hasActiveImportProcess ? "加入队列" : "开始分析"}
                </button>
              </form>
              {importResult && (
                <div className={importResult.duplicate ? "notice warning" : "notice"}>
                  <strong>{statusText(importResult.status)}</strong>
                  <span>
                    {importResult.duplicate
                      ? `${importResult.existing_slug} 已存在`
                      : `${hasActiveImportProcess ? "已加入分析队列" : "已开始分析"} · arXiv ${importResult.arxiv_id}`}
                  </span>
                </div>
              )}
              {error && (
                <div className="notice error">
                  <AlertCircle size={18} />
                  <span>{error}</span>
                </div>
              )}
              {importPreviewPaper && (
                <article className="import-preview-card" aria-label="导入完成预览">
                  <div className="import-preview-copy">
                    <span className="preview-kicker">
                      {activeImportPaper ? "🔄 当前论文" : "✅ 导入成功"}
                    </span>
                    <h3>{paperTitle(importPreviewPaper)}</h3>
                    <p>{importPreviewPaper.abstract || "AI 会把论文整理成结构化中文报告，并自动写入本地文献库。"}</p>
                    <div className="preview-meta">
                      <span>{importPreviewPaper.arxiv_id || "arXiv"}</span>
                      <span>{importPreviewPaper.research_line || "未分类"}</span>
                      <span>{importPreviewPaper.has_code ? "有代码" : "无代码"}</span>
                    </div>
                    <div className="row-tags">
                      {[...compactTags(importPreviewPaper, "topic", 2), ...compactTags(importPreviewPaper, "method", 2)].map((tag) => (
                        <span key={`preview-${tag}`}>{tag}</span>
                      ))}
                    </div>
                  </div>
                  <div className="import-preview-actions">
                    {importPreviewPaper.report_html_path && (
                      <button className="action-button action-primary" type="button" onClick={() => openReportInApp(importPreviewPaper)}>
                        阅读报告
                      </button>
                    )}
                    <button className="action-button action-secondary" type="button" onClick={() => selectPaper(importPreviewPaper.slug)}>
                      查看详情
                    </button>
                  </div>
                </article>
              )}
            </div>

            <aside className={`import-status${isImportJobLive ? " live" : ""}`} aria-label="当前分析进度">
              <div className="import-status-head">
                <div>
                  <span>当前任务</span>
                  <strong>{isImportJobPaused ? "已暂停" : activeImportJob ? stepText(activeImportJob.current_step) : "等待导入"}</strong>
                  {activeImportElapsed && (
                    <em className="elapsed-time">{activeImportElapsedLabel} {activeImportElapsed}</em>
                  )}
                  {settings?.llm_provider === "claude-code" && isImportJobLive && (
                    <span className="claude-mode-hint">⚡ Claude Code 模式：包含子 agent 分析，预计需要 5-10 分钟</span>
                  )}
                </div>
                <div className="import-status-meter">
                  <b>{activeImportJob ? `${activeImportJob.progress || 0}%` : "0%"}</b>
                  <span className={`live-indicator${isImportJobLive ? " is-live" : ""}`}>
                    <i />
                    {isImportJobLive ? "实时同步" : isImportJobPaused ? "已暂停" : activeImportJob?.status === "completed" ? "已完成" : activeImportJob?.status === "canceled" ? "已取消" : "待开始"}
                  </span>
                </div>
              </div>
              <div className={`progress-track large${isImportJobLive ? " live" : ""}`}>
                <span style={{ width: `${activeImportJob?.progress || 0}%` }} />
              </div>
              <div className="import-stepper">
                {IMPORT_STEPS.map(([step, label], index) => {
                  const currentIndex = importStepIndex(activeImportJob?.current_step);
                  const state = activeImportJob?.current_step === "completed" || index < currentIndex
                    ? "done"
                    : index === currentIndex
                      ? "current"
                      : "pending";
                  return (
                    <span className={`step-dot ${state}${state === "current" && isImportJobLive ? " live" : ""}`} key={step}>
                      <i>{index + 1}</i>
                      <em>{label}</em>
                    </span>
                  );
                })}
              </div>
              {activeImportJob && (
                <div className="activity-feed" aria-label="任务活动记录">
                  <div className="activity-feed-head">
                    <span>活动记录</span>
                    <b>{isImportJobLive ? "同步中" : "最近记录"}</b>
                  </div>
                  {activeImportActivityItems.length > 0 ? (
                    <ol>
                      {activeImportActivityItems.map((log, index) => (
                        <li key={`${activeImportJob.id}-${index}`}>{log}</li>
                      ))}
                    </ol>
                  ) : (
                    <p>开始后会记录每个处理阶段。</p>
                  )}
                </div>
              )}
              {activeImportJob && ["queued", "running", "needs_llm", "paused", "failed"].includes(activeImportJob.status) && (
                <div className="import-job-actions">
                  {["paused", "needs_llm", "failed"].includes(activeImportJob.status) ? (
                    <button className="small-button" type="button" onClick={() => resumeJob(activeImportJob.id)}>
                      <Play size={15} />
                      继续分析
                    </button>
                  ) : (
                    <button className="small-button ghost-button" type="button" onClick={() => pauseJob(activeImportJob.id)}>
                      <Pause size={15} />
                      暂停
                    </button>
                  )}
                  <button className="small-button ghost-button danger-button" type="button" onClick={() => cancelJob(activeImportJob.id)}>
                    <X size={15} />
                    取消并修改链接
                  </button>
                </div>
              )}
              <p className="import-status-note">
                {activeImportPaper
                  ? joinDistinctTitleMeta(paperTitle(activeImportPaper), activeImportPaper.slug)
                  : activeImportJob
                    ? joinDistinctTitleMeta(jobPaperTitle(activeImportJob), jobPaperMeta(activeImportJob))
                    : "开始后这里会显示实时分析阶段。"}
              </p>
              {queuedImportJobs.length > 0 && (
                <div className="import-queue-list" aria-label="等待分析队列">
                  <div className="import-queue-head">
                    <span>等待队列</span>
                    <b>{queuedImportJobs.length} 篇</b>
                  </div>
                  <ol>
                    {queuedImportJobs.slice(0, 5).map((job, index) => (
                      <li key={job.id}>
                        <i>{index + 1}</i>
                        <span>{joinDistinctTitleMeta(jobPaperTitle(job), jobPaperMeta(job))}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {activeImportJob?.status === "paused" && (
                <div className="notice warning compact-notice">
                  <span>当前分析已暂停，可以继续，或取消后换一个链接。</span>
                </div>
              )}
              {activeImportJob?.status === "needs_llm" && (
                <div className="notice warning compact-notice">
                  <span>需要先在设置里补充模型或 API 密钥。</span>
                </div>
              )}
              {activeImportJob?.error_message && (
                <p className="inline-error">{activeImportJob.error_message.split("\n")[0]}</p>
              )}
            </aside>
          </div>
          {recentCompletedPapers.length > 0 && (
            <section className="recent-imports" aria-label="最近完成文献">
              <div className="recent-imports-head">
                <strong>最近完成文献</strong>
                <span>最多显示 3 篇</span>
              </div>
              <div className="recent-import-list">
                {recentCompletedPapers.map((paper) => (
                  <article className="recent-import" key={paper.slug}>
                    <span>{statusText(paper.status)}</span>
                    <div>
                      <strong>{paperTitle(paper)}</strong>
                      <small>{paper.slug}</small>
                    </div>
                    <button className="action-button action-secondary" type="button" onClick={() => openReportInApp(paper)}>
                      阅读
                    </button>
                  </article>
                ))}
              </div>
            </section>
          )}
        </section>}

        {activeView === "settings" && <section id="settings" className="panel settings-panel">
          <form className="settings-form" onSubmit={saveSettings}>
            <div className="settings-intro">
              <span>AI 阅读配置</span>
              <p>选择一种 AI Provider，只能启用一种模式：</p>
            </div>
            <div className="provider-mode-cards" aria-label="选择 AI Provider">
              <button
                className={`provider-card${provider === "openai" ? " active" : ""}`}
                type="button"
                onClick={() => setProvider("openai")}
              >
                <strong>🤖 OpenAI 兼容 API</strong>
                <span>需要 API Key</span>
                <small>支持多个配置档案切换</small>
              </button>
              <button
                className={`provider-card${provider === "claude-code" ? " active" : ""}`}
                type="button"
                onClick={() => {
                  setProvider("claude-code");
                  if (claudeProfiles.length > 0 && !selectedClaudeProfile) {
                    setSelectedClaudeProfile(claudeProfiles[0].id);
                  }
                }}
              >
                <strong>⚡ Claude Code</strong>
                <span>本地 CLI，自带 harness</span>
                <small>子 agent + 工具使用 + 迭代修正，读论文质量更高</small>
              </button>
            </div>
            <section className="api-settings-workspace" aria-label="AI 连接配置">
              <div className="api-current-card">
                <div className="api-card-head">
                  <strong>当前连接</strong>
                  <span>用于生成中文阅读报告</span>
                </div>
                {provider === "claude-code" ? (
                  <>
                    <label className="setting-field">
                      Claude Code Profile
                      {claudeProfiles.length > 0 ? (
                        <select
                          value={selectedClaudeProfile}
                          onChange={(event) => setSelectedClaudeProfile(event.target.value)}
                        >
                          {claudeProfiles.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name} ({p.model})
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="setting-hint">未找到 Claude Code profiles，请先在 ~/.claude/profiles/ 下创建 .env 文件</span>
                      )}
                    </label>
                    <div className="claude-profile-info">
                      {selectedClaudeProfile && claudeProfiles.find(p => p.id === selectedClaudeProfile) && (
                        <small>
                          模型: {claudeProfiles.find(p => p.id === selectedClaudeProfile)?.model} ·
                          端点: {claudeProfiles.find(p => p.id === selectedClaudeProfile)?.base_url}
                        </small>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <label className="setting-field">
                      API 密钥
                      <div className="secret-input-row">
                        <input
                          value={apiKey}
                          onChange={(event) => setApiKey(event.target.value)}
                          placeholder={settings?.openai_api_key_set ? "已配置，留空则不修改" : "粘贴 API Key"}
                          type={showApiKey ? "text" : "password"}
                        />
                        <button
                          className="small-button secret-toggle-button"
                          type="button"
                          aria-pressed={showApiKey}
                          onClick={() => setShowApiKey((visible) => !visible)}
                        >
                          {showApiKey ? "隐藏" : "显示"}
                        </button>
                      </div>
                    </label>
                    <div className="api-two-column">
                      <label className="setting-field">
                        报告模型
                        <input value={model} onChange={(event) => setModel(event.target.value)} placeholder="gpt-4.1" />
                  </label>
                  <label className="setting-field">
                    接口地址
                    <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" />
                  </label>
                </div>
                  </>
                )}
                <div className="api-action-strip">
                {provider !== "claude-code" && (
                <div className="api-profile-save">
                  <input
                    value={profileName}
                    onChange={(event) => setProfileName(event.target.value)}
                    placeholder="配置名称，例如：OpenAI / 实验室网关"
                  />
                  <button className="small-button" type="button" onClick={saveCurrentApiProfile}>
                    保存为配置
                  </button>
                </div>
                )}
                <div className="settings-actions">
                  <button className="primary-button" type="submit">保存设置</button>
                  <button className="small-button api-test-button" type="button" disabled={apiTestStatus === "testing"} onClick={testApiConnection}>
                    {apiTestStatus === "testing" ? "测试中" : "测试连接"}
                  </button>
                </div>
                {apiTestMessage && (
                  <div className={`api-test-result ${apiTestStatus}`}>
                    <span>{apiTestMessage}</span>
                    {apiTestStatus === "error" && apiTestDetail && (
                      <button className="small-button ghost-button" type="button" onClick={() => setShowApiTestDetail(true)}>
                        查看详情
                      </button>
                    )}
                  </div>
                )}
                </div>
              </div>
              {provider !== "claude-code" && (
              <div className="api-profile-manager" aria-label="API 密钥管理">
                <div className="api-profile-head">
                  <div>
                    <strong>API 配置档案</strong>
                    <span>最多启用一个配置；再次点击开关可关闭。</span>
                  </div>
                </div>
              {apiProfiles.length > 0 ? (
                <div className="api-profile-list">
                  {apiProfiles.map((profile) => (
                    <article className={profile.is_active ? "api-profile-card active" : "api-profile-card"} key={profile.id}>
                      <div>
                        <strong>{profile.name}</strong>
                        <span>{profile.llm_model} · {profile.llm_provider}</span>
                        <small>{profile.openai_base_url}</small>
                      </div>
                      <div className="api-profile-actions">
                        <button
                          className={profile.is_active ? "profile-switch active" : "profile-switch"}
                          type="button"
                          role="switch"
                          aria-checked={profile.is_active}
                          title={profile.is_active ? "关闭启用" : "启用该配置"}
                          onClick={() => toggleApiProfile(profile)}
                        >
                          <span />
                        </button>
                        <button className="small-button" type="button" disabled={apiProfileTests[profile.id]?.status === "testing"} onClick={() => testApiProfile(profile)}>
                          {apiProfileTests[profile.id]?.status === "testing" ? "测试中" : "测试"}
                        </button>
                        <button className="small-button ghost-button" type="button" onClick={() => startEditingApiProfile(profile)}>
                          编辑
                        </button>
                        <button className="small-button ghost-button" type="button" onClick={() => deleteApiProfile(profile.id)}>
                          删除
                        </button>
                      </div>
                      {editingApiProfileId === profile.id && (
                        <div className="api-profile-editor">
                          <label>
                            配置名称
                            <input
                              value={editingProfileName}
                              onChange={(event) => setEditingProfileName(event.target.value)}
                              placeholder="例如：OpenAI / 实验室网关"
                            />
                          </label>
                          <label>
                            报告模型
                            <input
                              value={editingProfileModel}
                              onChange={(event) => setEditingProfileModel(event.target.value)}
                              placeholder="例如：gpt-4.1"
                            />
                          </label>
                          <label>
                            接口地址
                            <input
                              value={editingProfileBaseUrl}
                              onChange={(event) => setEditingProfileBaseUrl(event.target.value)}
                              placeholder="例如：https://api.openai.com/v1"
                            />
                          </label>
                          <label>
                            API 密钥
                            <input
                              value={editingProfileApiKey}
                              onChange={(event) => setEditingProfileApiKey(event.target.value)}
                              placeholder={profile.api_key_set ? "已配置，留空则沿用" : "粘贴 API Key"}
                              type="password"
                            />
                          </label>
                          <div className="api-profile-editor-actions">
                            <button className="small-button filter-apply-button" type="button" onClick={() => saveEditedApiProfile(profile)}>
                              保存修改
                            </button>
                            <button className="small-button ghost-button" type="button" onClick={cancelEditingApiProfile}>
                              取消
                            </button>
                          </div>
                        </div>
                      )}
                      {apiProfileTests[profile.id] && (
                        <div className={`profile-test-result ${apiProfileTests[profile.id].status}`}>
                          <span>{apiProfileTests[profile.id].message}</span>
                          {apiProfileTests[profile.id].status === "error" && apiProfileTests[profile.id].detail && (
                            <button
                              className="small-button ghost-button"
                              type="button"
                              onClick={() => {
                                setApiTestDetail(apiProfileTests[profile.id].detail || "");
                                setShowApiTestDetail(true);
                              }}
                            >
                              查看详情
                            </button>
                          )}
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              ) : (
                <p className="api-profile-empty">还没有保存的 API 配置。填好上面的模型与密钥后，可以保存成一个配置。</p>
              )}
              </div>
              )}
            </section>
            <details className="advanced-panel settings-advanced">
              <summary>
                <span>
                  <strong>本地存储目录</strong>
                  <small>设置源码与报告保存位置，适合打包后换机器使用。</small>
                </span>
                <b>展开</b>
              </summary>
              <div className="settings-primary">
                <label className="setting-field wide">
                  源码目录
                  <div className="path-input-row">
                    <input
                      value={sourceDir}
                      onChange={(event) => setSourceDir(event.target.value)}
                      placeholder="例如：~/AutoPaperReader/sources"
                    />
                    <button className="small-button path-picker-button" type="button" disabled={pickingDirectory === "source"} onClick={() => chooseDirectory("source")}>
                      <FolderOpen size={15} />
                      <span>{pickingDirectory === "source" ? "选择中" : "选择"}</span>
                    </button>
                  </div>
                </label>
                <label className="setting-field wide">
                  报告目录
                  <div className="path-input-row">
                    <input
                      value={reportDir}
                      onChange={(event) => setReportDir(event.target.value)}
                      placeholder="例如：~/AutoPaperReader/reports"
                    />
                    <button className="small-button path-picker-button" type="button" disabled={pickingDirectory === "report"} onClick={() => chooseDirectory("report")}>
                      <FolderOpen size={15} />
                      <span>{pickingDirectory === "report" ? "选择中" : "选择"}</span>
                    </button>
                  </div>
                </label>
              </div>
            </details>
            <details className="advanced-panel settings-advanced">
              <summary>
                <span>
                  <strong>语义搜索配置</strong>
                  <small>可选。启用后支持按语义查找相似论文。</small>
                </span>
                <b>展开</b>
              </summary>
              <div className="settings-primary compact">
                <label className="setting-field">
                  向量供应商
                  <input
                    value={embeddingProvider}
                    onChange={(event) => setEmbeddingProvider(event.target.value)}
                    placeholder="留空则关闭"
                  />
                </label>
                <label className="setting-field">
                  向量模型
                  <input
                    value={embeddingModel}
                    onChange={(event) => setEmbeddingModel(event.target.value)}
                    placeholder="hashing-v1"
                  />
                </label>
                <label className="setting-field">
                  向量维度
                  <input
                    value={embeddingDimension}
                    onChange={(event) => setEmbeddingDimension(event.target.value)}
                    placeholder="64"
                  />
                </label>
              </div>
            </details>
          </form>
          {settings && (
            <div className="settings-meta" aria-label="当前本地配置">
              <span>当前存储</span>
              <dl>
                <div title={settings.report_dir}><dt>报告</dt><dd>{settings.report_dir}</dd></div>
                <div title={settings.source_dir}><dt>源码</dt><dd>{settings.source_dir}</dd></div>
                <div title={settings.db_path}><dt>数据库</dt><dd>{settings.db_path}</dd></div>
                <div><dt>语义搜索</dt><dd>{settings.embedding_enabled ? "已启用" : "未启用"}</dd></div>
              </dl>
            </div>
          )}
        </section>}

        {activeView === "library" && <>
          <div className="field-filter-bar" aria-label="领域筛选">
              <div className="field-filter-heading">
                <GitBranch size={18} />
                <strong>领域</strong>
              </div>
              <button
                className={selectedResearchLine === ALL_RESEARCH_LINES ? "field-filter compact active" : "field-filter compact"}
                type="button"
                onClick={() => chooseResearchLine(ALL_RESEARCH_LINES)}
              >
                <span>全部</span>
                <b>{allResearchLineCount || papers.length}</b>
              </button>
              {(unassignedResearchLine || papers.some((paper) => !paper.research_line)) && (
                <button
                  className={selectedResearchLine === UNASSIGNED_RESEARCH_LINE ? "field-filter compact active" : "field-filter compact"}
                  type="button"
                  onClick={() => chooseResearchLine(UNASSIGNED_RESEARCH_LINE)}
                >
                  <span>未分类</span>
                  <b>{unassignedResearchLineCount}</b>
                </button>
              )}
              <label className="field-select-wrap toolbar-control" htmlFor="research-line-select">
                <span>按领域筛选</span>
                <select
                  id="research-line-select"
                  value={
                    selectedResearchLine === ALL_RESEARCH_LINES || selectedResearchLine === UNASSIGNED_RESEARCH_LINE
                      ? ""
                      : selectedResearchLine
                  }
                  onChange={(event) => {
                    if (event.target.value) chooseResearchLine(event.target.value);
                  }}
                >
                  <option value="">选择领域</option>
                  {namedResearchLines.map((line) => (
                    <option key={line.name} value={line.name}>
                      {researchLineLabel(line.name)}（{line.count}）
                    </option>
                  ))}
                </select>
              </label>
              <form className="library-quick-search" onSubmit={searchLibrary} aria-label="文献搜索">
                <div className="search-mode-switch" role="group" aria-label="搜索方式">
                  <button
                    className={searchKind === "keyword" ? "search-mode-option active" : "search-mode-option"}
                    type="button"
                    onClick={() => setSearchKind("keyword")}
                  >
                    全文
                  </button>
                  <button
                    className={searchKind === "semantic" ? "search-mode-option active" : "search-mode-option"}
                    type="button"
                    onClick={() => setSearchKind("semantic")}
                  >
                    语义
                  </button>
                </div>
                <input
                  aria-label={searchKind === "semantic" ? "语义相似搜索" : "全文搜索"}
                  className="toolbar-control"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder={searchKind === "semantic" ? "语义相似：找和 draft token verification 相近的论文" : "全文搜索：speculative decoding verification"}
                />
                <button className="primary-button" type="submit">
                  <Search size={17} />
                  <span>{searchKind === "semantic" ? "找相似" : "搜索"}</span>
                </button>
                {searchMode && (
                  <button className="small-button" type="button" onClick={() => {
                    setSearchQuery("");
                    refreshPapers();
                  }}>
                  清除
                </button>
              )}
            </form>
              {semanticNotice && <p className="inline-note library-search-note">{semanticNotice}</p>}
          </div>
          <section id="library" className="panel library-panel">
          <div className="library-main">
          <details className="advanced-panel library-filter-panel">
            <summary>
              <span>
                <strong>精细筛选</strong>
                <small>{activeFilterCount ? `已启用 ${activeFilterCount} 个条件` : "未设置条件"}</small>
              </span>
              <b>展开</b>
            </summary>
            <div className="filter-row">
              <label>
                状态
                <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="">全部</option>
                  <option value="unread">未读</option>
                  <option value="reading">阅读中</option>
                  <option value="read">已读</option>
                  <option value="archived">已归档</option>
                </select>
              </label>
              <label>
                重要性
                <select value={importanceFilter} onChange={(event) => setImportanceFilter(event.target.value)}>
                  <option value="">全部</option>
                  <option value="5">5</option>
                  <option value="4">4</option>
                  <option value="3">3</option>
                  <option value="2">2</option>
                  <option value="1">1</option>
                </select>
              </label>
              <label>
                代码
                <select value={codeFilter} onChange={(event) => setCodeFilter(event.target.value)}>
                  <option value="">全部</option>
                  <option value="yes">已检测到</option>
                  <option value="no">无</option>
                </select>
              </label>
              <label>
                主题
                <input
                  value={topicFilter}
                  onChange={(event) => setTopicFilter(event.target.value)}
                  placeholder="例如：RAG / Reasoning"
                />
              </label>
              <label>
                方法
                <input
                  value={methodFilter}
                  onChange={(event) => setMethodFilter(event.target.value)}
                  placeholder="例如：MoE / KV cache"
                />
              </label>
              <div className="filter-actions">
                <button className="small-button filter-apply-button" type="button" onClick={refreshPapers}>
                  应用筛选
                </button>
                <button className="small-button ghost-button" type="button" onClick={clearFilters}>
                  重置
                </button>
                <button className="small-button ghost-button filter-index-button" type="button" onClick={rebuildSemanticIndex}>
                  重建索引
                </button>
              </div>
            </div>
          </details>
          <div className="library-toolbar">
            <div className="view-switch" aria-label="文献显示方式">
              <span className="toolbar-label">显示方式</span>
              <button
                className={libraryLayout === "list" ? "view-option active" : "view-option"}
                type="button"
                onClick={() => setLibraryLayout("list")}
              >
                <List size={16} />
                <span>列表</span>
              </button>
              <button
                className={libraryLayout === "cards" ? "view-option active" : "view-option"}
                type="button"
                onClick={() => setLibraryLayout("cards")}
              >
                <LayoutGrid size={16} />
                <span>卡片</span>
              </button>
            </div>
            <div className={bulkEditMode ? "bulk-toolbar active" : "bulk-toolbar"}>
              {!bulkEditMode ? (
                <button className="bulk-entry-button" type="button" onClick={() => setBulkEditMode(true)}>
                  <CheckSquare size={16} />
                  <span>批量编辑领域</span>
                </button>
              ) : (
                <>
                  <div className="bulk-summary">
                    <CheckSquare size={16} />
                    <span>{selectedPaperRows.length ? `已选 ${selectedPaperRows.length} 篇论文` : "选择论文后设置领域"}</span>
                  </div>
                  <input
                    list="research-line-options"
                    value={bulkResearchLine}
                    onChange={(event) => setBulkResearchLine(event.target.value)}
                    placeholder={selectedPaperRows.length ? "输入或选择领域" : "先选择论文"}
                    disabled={!selectedPaperRows.length}
                  />
                  <datalist id="research-line-options">
                    {namedResearchLines.map((line) => (
                      <option key={line.name} value={line.name} />
                    ))}
                  </datalist>
                  <button className="small-button" type="button" disabled={!selectedPaperRows.length || !bulkResearchLine.trim()} onClick={applyBulkResearchLine}>
                    设置领域
                  </button>
                  <button className="small-button ghost-button danger-button" type="button" disabled={!selectedPaperRows.length} onClick={deleteSelectedPapers}>
                    <Trash2 size={15} />
                    删除所选
                  </button>
                  {selectedPaperRows.length > 0 && (
                    <button className="small-button" type="button" onClick={() => setSelectedSlugs([])}>
                      清空选择
                    </button>
                  )}
                  <button
                    className="small-button ghost-button"
                    type="button"
                    onClick={() => {
                      setBulkEditMode(false);
                      setSelectedSlugs([]);
                      setBulkResearchLine("");
                    }}
                  >
                    退出编辑
                  </button>
                </>
              )}
            </div>
          </div>
          {libraryNotice && <p className="inline-note">{libraryNotice}</p>}
          {papers.length === 0 && (
            <div className="empty-state">
              <p>SQLite 里还没有论文。</p>
              <button className="small-button" type="button" onClick={() => setActiveView("import")}>
                去导入第一篇
              </button>
            </div>
          )}
          {libraryLayout === "list" && papers.length > 0 && (
            <div className={bulkEditMode ? "paper-list editing" : "paper-list"}>
              <div className="paper-list-header">
                {bulkEditMode ? (
                  <label className="select-all-row">
                    <input
                      aria-label="选择当前列表全部论文"
                      checked={allVisibleSelected}
                      type="checkbox"
                      onChange={toggleAllVisiblePapers}
                    />
                    <span>选择当前列表</span>
                  </label>
                ) : (
                  <span>浏览模式</span>
                )}
                <span>{papers.length} 篇论文</span>
              </div>
              {papers.map((paper) => (
                <article className={`${selectedSlugs.includes(paper.slug) ? "paper-row selected" : "paper-row"}${bulkEditMode ? " selectable" : ""}`} key={paper.slug}>
                  {bulkEditMode && (
                    <label className="row-check">
                      <input
                        aria-label={`选择 ${paperTitle(paper)}`}
                        checked={selectedSlugs.includes(paper.slug)}
                        type="checkbox"
                        onChange={() => toggleSelectedPaper(paper.slug)}
                      />
                    </label>
                  )}
                  <div className="row-main">
                    <button className="row-title-button" type="button" onClick={() => selectPaper(paper.slug)}>
                      <strong>{paperTitle(paper)}</strong>
                      <span>{paper.slug}</span>
                    </button>
                    <div className="row-meta">
                      <span>{paper.year || "年份未知"}</span>
                      <span>{paper.research_line || "未分类"}</span>
                      <span>{statusText(paper.status)}</span>
                      <span>重要性 {paper.importance || "-"}</span>
                      <span>{paper.has_code ? "有代码" : "无代码"}</span>
                      {paper.score !== undefined && <span>相似度 {paper.score.toFixed(3)}</span>}
                    </div>
                    <div className="row-tags">
                      {[...compactTags(paper, "topic", 2), ...compactTags(paper, "method", 2)].map((tag) => (
                        <span key={`${paper.slug}-${tag}`}>{tag}</span>
                      ))}
                      {!compactTags(paper, "topic").length && !compactTags(paper, "method").length && (
                        <span>暂无标签</span>
                      )}
                    </div>
                  </div>
                  <div className="row-actions">
                    {paper.report_html_path && (
                      <button className="action-button action-primary" type="button" onClick={() => openReportInApp(paper)}>
                        阅读
                      </button>
                    )}
                    <button className="action-button action-secondary" type="button" onClick={() => selectPaper(paper.slug)}>
                      详情
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
          {libraryLayout === "cards" && papers.length > 0 && (
            <div className="paper-grid">
              {papers.map((paper) => (
                <article className="paper-card" key={paper.slug}>
                  <div className="paper-card-header">
                    <div className="paper-title">
                      <strong>{paperTitle(paper)}</strong>
                      <span>{paper.slug}</span>
                    </div>
                    <span className="status-pill">{statusText(paper.status)}</span>
                  </div>
                  <div className="paper-meta-row">
                    <span>{paper.year || "年份未知"}</span>
                    <span>{paper.research_line || "未分类"}</span>
                    <span>{paper.has_code ? "有代码" : "无代码"}</span>
                    {paper.score !== undefined && <span>相似度 {paper.score.toFixed(3)}</span>}
                  </div>
                  <div className="tag-list">
                    {[...compactTags(paper, "topic", 3), ...compactTags(paper, "method", 2)].map((tag) => (
                      <span key={`${paper.slug}-${tag}`}>{tag}</span>
                    ))}
                    {!compactTags(paper, "topic").length && !compactTags(paper, "method").length && (
                      <span>暂无标签</span>
                    )}
                  </div>
                  {paper.matched_chunk && <p className="matched-chunk">{paper.matched_chunk}</p>}
                  <div className="paper-actions">
                    {paper.report_html_path ? (
                      <button className="action-button action-primary" type="button" onClick={() => openReportInApp(paper)}>
                        <BookOpen size={15} /> 阅读报告
                      </button>
                    ) : (
                      <button className="action-button action-primary" type="button" onClick={() => selectPaper(paper.slug)}>
                        详情
                      </button>
                    )}
                    <button className="action-button action-secondary" type="button" onClick={() => selectPaper(paper.slug)}>
                      详情/分类
                    </button>
                    {paper.code_url && (
                      <a className="action-button action-ghost" href={paper.code_url} target="_blank" rel="noreferrer">
                        代码
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
          </div>
        </section>
        </>}

        {selectedPaper && (
          <aside className="detail-drawer" aria-label="论文详情">
            <div className="drawer-header">
              <div>
                <p className="eyebrow">论文详情</p>
                <h2>{paperTitle(selectedPaper)}</h2>
              </div>
              <button className="icon-button" onClick={() => setSelectedPaper(null)} title="关闭详情">
                <X size={18} />
              </button>
            </div>
            <div className="drawer-actions">
              {selectedPaper.report_html_path && (
                <button className="action-button action-primary" type="button" onClick={() => openReportInApp(selectedPaper)}>
                  <BookOpen size={15} /> 打开完整报告
                </button>
              )}
              {selectedPaper.report_md_path && (
                <a className="action-button action-secondary" href={fileUrl(selectedPaper.report_md_path)} target="_blank" rel="noreferrer">
                  Markdown
                </a>
              )}
            </div>
            <dl className="compact-dl">
              <div><dt>标识</dt><dd>{selectedPaper.slug}</dd></div>
              <div><dt>arXiv</dt><dd>{selectedPaper.arxiv_id || "未知"}</dd></div>
              <div><dt>年份</dt><dd>{selectedPaper.year || "未知"}</dd></div>
              <div><dt>状态</dt><dd>{statusText(selectedPaper.status)}</dd></div>
              <div><dt>阅读阶段</dt><dd>{stageText(selectedPaper.reading_stage)}</dd></div>
              <div><dt>领域</dt><dd>{selectedPaper.research_line || "未分类"}</dd></div>
              <div><dt>主题</dt><dd>{selectedPaper.tags?.topic?.join(", ") || "未分配"}</dd></div>
              <div><dt>方法</dt><dd>{selectedPaper.tags?.method?.join(", ") || "未分配"}</dd></div>
              <div><dt>作者</dt><dd>{(selectedPaper.authors || []).join(", ") || "未知"}</dd></div>
            </dl>
            <div className="link-row">
              {selectedPaper.arxiv_url && (
                <a href={selectedPaper.arxiv_url} target="_blank" rel="noreferrer">
                  <ExternalLink size={15} /> arXiv
                </a>
              )}
              {selectedPaper.pdf_url && (
                <a href={selectedPaper.pdf_url} target="_blank" rel="noreferrer">
                  <ExternalLink size={15} /> PDF
                </a>
              )}
              {selectedPaper.code_url && (
                <a href={selectedPaper.code_url} target="_blank" rel="noreferrer">
                  <ExternalLink size={15} /> 代码
                </a>
              )}
            </div>
            {selectedPaper.abstract && <p className="paper-abstract">{selectedPaper.abstract}</p>}
            <form className="classification-form" onSubmit={saveClassification}>
              <h3>分类</h3>
              <label>
                领域
                <input
                  value={classificationLine}
                  onChange={(event) => setClassificationLine(event.target.value)}
                  placeholder="例如：RAG / LLM Serving / Reasoning"
                />
              </label>
              <label>
                领域角色
                <input
                  value={classificationRole}
                  onChange={(event) => setClassificationRole(event.target.value)}
                  placeholder="main / baseline / survey / application"
                />
              </label>
              <label>
                主题
                <input
                  value={classificationTopics}
                  onChange={(event) => setClassificationTopics(event.target.value)}
                  placeholder="多个主题用逗号分隔"
                />
              </label>
              <label>
                方法
                <input
                  value={classificationMethods}
                  onChange={(event) => setClassificationMethods(event.target.value)}
                  placeholder="多个方法用逗号分隔"
                />
              </label>
              <div className="classification-actions">
                <button className="primary-button" type="submit">保存分类</button>
                {classificationNotice && <span>{classificationNotice}</span>}
              </div>
            </form>
          </aside>
        )}

        {showApiTestDetail && apiTestDetail && (
          <section className="api-error-modal" role="dialog" aria-modal="true" aria-label="API 测试错误详情">
            <div className="api-error-backdrop" onClick={() => setShowApiTestDetail(false)} />
            <div className="api-error-dialog">
              <header>
                <div>
                  <p className="eyebrow">测试连接</p>
                  <h2>API 错误详情</h2>
                </div>
                <button className="icon-button" type="button" onClick={() => setShowApiTestDetail(false)} title="关闭">
                  <X size={18} />
                </button>
              </header>
              <p className="api-error-summary">{summarizeApiFeedback(apiTestDetail)}</p>
              <pre>{apiTestDetail}</pre>
              <div className="api-error-actions">
                <button className="small-button" type="button" onClick={() => navigator.clipboard?.writeText(apiTestDetail)}>
                  复制错误
                </button>
                <button className="primary-button" type="button" onClick={() => setShowApiTestDetail(false)}>
                  关闭
                </button>
              </div>
            </div>
          </section>
        )}

        {reportPaper?.report_html_path && (
          <section className="report-viewer" aria-label="阅读报告">
            <header className="report-viewer-header">
              <div>
                <p className="eyebrow">阅读报告</p>
                <h2>{paperTitle(reportPaper)}</h2>
              </div>
              <div className="report-viewer-actions">
                <button className="action-button action-secondary" type="button" onClick={() => openDetailsFromReport(reportPaper)}>
                  详情/分类
                </button>
                <a className="action-button action-secondary" href={fileUrl(reportPaper.report_html_path)} target="_blank" rel="noreferrer">
                  外部打开
                </a>
                <button className="icon-button" type="button" onClick={() => setReportPaper(null)} title="关闭阅读报告">
                  <X size={18} />
                </button>
              </div>
            </header>
            <iframe
              className="report-frame"
              src={fileUrl(reportPaper.report_html_path)}
              title={`阅读报告：${paperTitle(reportPaper)}`}
            />
          </section>
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
