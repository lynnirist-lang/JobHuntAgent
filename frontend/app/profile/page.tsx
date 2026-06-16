"use client";

import { useRef, useState, useEffect } from "react";

const card: React.CSSProperties = {
  background: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: 20,
  marginBottom: 16,
};

const cardTitle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: "var(--fg)",
  marginBottom: 14,
  paddingBottom: 10,
  borderBottom: "1px solid var(--border)",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const inputStyle: React.CSSProperties = {
  background: "var(--card2)",
  border: "1px solid var(--border2)",
  borderRadius: "var(--radius-sm)",
  color: "var(--fg)",
  fontSize: 13,
  padding: "8px 12px",
  outline: "none",
  width: "100%",
  marginBottom: 10,
};

const lbl: React.CSSProperties = {
  fontSize: 11,
  color: "var(--muted)",
  marginBottom: 4,
  display: "block",
};

const iconBtn = (color: string): React.CSSProperties => ({
  background: "transparent",
  border: "none",
  color,
  cursor: "pointer",
  fontSize: 12,
  fontWeight: 600,
  padding: "3px 8px",
  borderRadius: 6,
  lineHeight: 1,
});

const INITIAL_SKILLS = ["Python", "FastAPI", "LangChain", "TypeScript", "Next.js", "Docker", "PostgreSQL", "Redis"];

interface ExpItem {
  company: string;
  role: string;
  duration: string;
  bullets: string[];
}

interface ProjItem {
  name: string;
  tech: string;
  github: string;
  bullets: string[];
}

const BLANK_EXP: ExpItem = { company: "", role: "", duration: "", bullets: [""] };
const BLANK_PROJ: ProjItem = { name: "", tech: "", github: "", bullets: [""] };

const INITIAL_EXPERIENCE: ExpItem[] = [
  {
    company: "某 AI 公司",
    role: "后端工程师",
    duration: "2022.06 — 至今",
    bullets: [
      "负责多个 LLM 应用的后端服务开发与优化",
      "设计并实现基于 RAG 的智能客服系统，响应延迟降低 40%",
      "主导微服务架构迁移，提升系统稳定性",
    ],
  },
  {
    company: "某互联网公司",
    role: "Python 开发实习生",
    duration: "2021.07 — 2022.05",
    bullets: [
      "参与数据管道开发，处理日均千万级数据",
      "开发内部自动化工具，节省人工成本 20%",
    ],
  },
];

const INITIAL_PROJECTS: ProjItem[] = [
  {
    name: "Job Hunt Agent",
    tech: "Next.js · FastAPI · Playwright · DeepSeek",
    github: "https://github.com",
    bullets: [
      "自动化 BOSS 直聘投递助手，支持 AI 生成个性化打招呼",
      "实现多账号管理和智能限速，规避封号风险",
    ],
  },
  {
    name: "RAG 知识库问答",
    tech: "LangChain · ChromaDB · GPT-4 · FastAPI",
    github: "https://github.com",
    bullets: [
      "基于向量检索的企业知识库问答系统",
      "支持 PDF/Word 文档自动解析和增量更新",
    ],
  },
];

/* ── Edit modal for experience ───────────────────────── */
function ExpEditor({
  item, onSave, onClose,
}: { item: ExpItem; onSave: (v: ExpItem) => void; onClose: () => void }) {
  const [v, setV] = useState<ExpItem>({ ...item, bullets: [...item.bullets] });
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)",
        zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        style={{ background: "var(--card)", borderRadius: "var(--radius)", padding: 24, width: 480, maxHeight: "80vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 16 }}>编辑工作经历</div>
        <span style={lbl}>公司</span>
        <input style={inputStyle} value={v.company} onChange={(e) => setV({ ...v, company: e.target.value })} />
        <span style={lbl}>职位</span>
        <input style={inputStyle} value={v.role} onChange={(e) => setV({ ...v, role: e.target.value })} />
        <span style={lbl}>时间段</span>
        <input style={inputStyle} value={v.duration} onChange={(e) => setV({ ...v, duration: e.target.value })} placeholder="2022.06 — 至今" />
        <span style={lbl}>工作描述（每行一条）</span>
        <textarea
          rows={5}
          value={v.bullets.join("\n")}
          onChange={(e) => setV({ ...v, bullets: e.target.value.split("\n") })}
          style={{ ...inputStyle, resize: "vertical" }}
        />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
          <button onClick={onClose} style={{ ...iconBtn("var(--muted)"), border: "1px solid var(--border2)", padding: "7px 16px" }}>取消</button>
          <button
            onClick={() => { onSave({ ...v, bullets: v.bullets.filter((b) => b.trim()) }); onClose(); }}
            style={{ background: "var(--accent)", color: "#fff", border: "none", borderRadius: 8, padding: "7px 18px", fontWeight: 700, fontSize: 13, cursor: "pointer" }}
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Edit modal for project ──────────────────────────── */
function ProjEditor({
  item, onSave, onClose,
}: { item: ProjItem; onSave: (v: ProjItem) => void; onClose: () => void }) {
  const [v, setV] = useState<ProjItem>({ ...item, bullets: [...item.bullets] });
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)",
        zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        style={{ background: "var(--card)", borderRadius: "var(--radius)", padding: 24, width: 480, maxHeight: "80vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 16 }}>编辑项目经历</div>
        <span style={lbl}>项目名称</span>
        <input style={inputStyle} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} />
        <span style={lbl}>技术栈</span>
        <input style={inputStyle} value={v.tech} onChange={(e) => setV({ ...v, tech: e.target.value })} placeholder="Next.js · FastAPI · …" />
        <span style={lbl}>GitHub 链接</span>
        <input style={inputStyle} value={v.github} onChange={(e) => setV({ ...v, github: e.target.value })} placeholder="https://github.com/…" />
        <span style={lbl}>项目亮点（每行一条）</span>
        <textarea
          rows={4}
          value={v.bullets.join("\n")}
          onChange={(e) => setV({ ...v, bullets: e.target.value.split("\n") })}
          style={{ ...inputStyle, resize: "vertical" }}
        />
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
          <button onClick={onClose} style={{ ...iconBtn("var(--muted)"), border: "1px solid var(--border2)", padding: "7px 16px" }}>取消</button>
          <button
            onClick={() => { onSave({ ...v, bullets: v.bullets.filter((b) => b.trim()) }); onClose(); }}
            style={{ background: "var(--accent)", color: "#fff", border: "none", borderRadius: 8, padding: "7px 18px", fontWeight: 700, fontSize: 13, cursor: "pointer" }}
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [skills, setSkills] = useState<string[]>(INITIAL_SKILLS);
  const [newSkill, setNewSkill] = useState("");
  const [saved, setSaved] = useState(false);

  // Basic info
  const [name, setName] = useState("张三");
  const [email, setEmail] = useState("zhangsan@example.com");
  const [phone, setPhone] = useState("138****0000");
  const [city, setCity] = useState("上海");
  const [bio, setBio] = useState("");

  // Intent
  const [targetRole, setTargetRole] = useState("后端工程师 / AI 工程师");
  const [targetCity, setTargetCity] = useState("上海 / 北京 / 远程");
  const [salaryExpect, setSalaryExpect] = useState("25k-40k");
  const [jobType, setJobType] = useState("全职");

  // Experience & Projects
  const [experiences, setExperiences] = useState<ExpItem[]>(INITIAL_EXPERIENCE);
  const [projects, setProjects] = useState<ProjItem[]>(INITIAL_PROJECTS);

  // Edit modal state
  const [editingExp, setEditingExp] = useState<{ idx: number; item: ExpItem } | null>(null);
  const [editingProj, setEditingProj] = useState<{ idx: number; item: ProjItem } | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/profile")
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (!data) return;
        const b = data.basic ?? {};
        if (b.name)  setName(b.name);
        if (b.email) setEmail(b.email);
        if (b.phone) setPhone(b.phone);
        if (b.city)  setCity(b.city);
        const t = data.target ?? {};
        if (t.roles?.length)  setTargetRole(t.roles.join(" / "));
        if (t.cities?.length) setTargetCity(t.cities.join(" / "));
        if (t.salary)         setSalaryExpect(t.salary);
        if (data.skills?.length)      setSkills(data.skills);
        if (data.experiences?.length) setExperiences(data.experiences);
        if (data.projects?.length)    setProjects(
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          data.projects.map((p: any) => ({ ...p, bullets: p.highlights ?? p.bullets ?? [] }))
        );
      })
      .catch(() => {/* backend may not be running */});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFileName(f.name);
    setUploading(true);
    setUploadMsg(null);
    try {
      const formData = new FormData();
      formData.append("file", f);
      const res = await fetch("/api/resume/upload", { method: "POST", body: formData });
      if (!res.ok) {
        let detail = `上传失败 (${res.status})`;
        try { const b = await res.json(); if (b?.detail) detail = b.detail; } catch { /* ignore */ }
        throw new Error(detail);
      }
      const data = await res.json();
      // Fill profile fields from parsed data if available
      if (data.name)  setName(data.name);
      if (data.email) setEmail(data.email);
      if (data.phone) setPhone(data.phone);
      if (data.city)  setCity(data.city);
      if (data.skills?.length)      setSkills(data.skills);
      if (data.experiences?.length) setExperiences(data.experiences);
      if (data.projects?.length)    setProjects(data.projects);
      setUploadMsg("✓ 简历已解析，字段已自动填充");
    } catch (err) {
      setUploadMsg(`解析失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setUploading(false);
    }
  };

  const handleReparse = async () => {
    if (!fileInputRef.current?.files?.[0]) return;
    const e = { target: fileInputRef.current } as React.ChangeEvent<HTMLInputElement>;
    await handleFileChange(e);
  };

  const addSkill = () => {
    const s = newSkill.trim();
    if (s && !skills.includes(s)) setSkills([...skills, s]);
    setNewSkill("");
  };
  const removeSkill = (s: string) => setSkills(skills.filter((k) => k !== s));

  const handleSave = async () => {
    setSaveError(null);
    const profile = {
      basic: { name, email, phone, city },
      target: { roles: targetRole.split("/").map((r) => r.trim()), cities: targetCity.split("/").map((c) => c.trim()), salary: salaryExpect },
      skills,
      experiences: experiences.map((e) => ({ company: e.company, role: e.role, duration: e.duration, bullets: e.bullets })),
      projects: projects.map((p) => ({ name: p.name, tech: p.tech, github: p.github, highlights: p.bullets })),
    };
    try {
      const res = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile }),
      });
      if (!res.ok) throw new Error(`保存失败 (${res.status})`);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* Edit modals */}
      {editingExp && (
        <ExpEditor
          item={editingExp.item}
          onSave={(v) => {
            setExperiences((prev) => {
              const next = [...prev];
              if (editingExp.idx === -1) next.push(v);
              else next[editingExp.idx] = v;
              return next;
            });
          }}
          onClose={() => setEditingExp(null)}
        />
      )}
      {editingProj && (
        <ProjEditor
          item={editingProj.item}
          onSave={(v) => {
            setProjects((prev) => {
              const next = [...prev];
              if (editingProj.idx === -1) next.push(v);
              else next[editingProj.idx] = v;
              return next;
            });
          }}
          onClose={() => setEditingProj(null)}
        />
      )}

      {/* Topbar */}
      <header
        style={{
          height: "var(--topbar-h)",
          borderBottom: "1px solid var(--border)",
          background: "var(--card)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 20px",
          position: "sticky",
          top: 0,
          zIndex: 40,
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 15 }}>个人档案</span>
      </header>

      {/* Content */}
      <div style={{ padding: "20px", overflowY: "auto", height: "calc(100vh - var(--topbar-h))" }}>
        <div style={{ maxWidth: 800 }}>

          {/* PDF upload zone */}
          <div style={{ ...card, marginBottom: 16 }}>
            <div style={cardTitle}>简历文件</div>
            {fileName ? (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  background: "var(--green-dim)",
                  border: "1px solid var(--green-border)",
                  borderRadius: "var(--radius-sm)",
                  padding: "12px 16px",
                }}
              >
                <span style={{ fontSize: 22 }}>📄</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg)" }}>{fileName}</div>
                  <div style={{ fontSize: 11, color: "var(--muted2)", marginTop: 2 }}>
                    {uploading ? "解析中…" : (uploadMsg || "已上传，可重新解析")}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    onClick={handleReparse}
                    disabled={uploading}
                    style={{
                      background: "var(--green-dim)",
                      border: "1px solid var(--green-border)",
                      color: "var(--green)",
                      borderRadius: 6,
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "5px 12px",
                      cursor: uploading ? "not-allowed" : "pointer",
                      opacity: uploading ? 0.6 : 1,
                    }}
                  >
                    {uploading ? "解析中…" : "重新解析"}
                  </button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    style={{
                      background: "transparent",
                      border: "1px solid var(--border2)",
                      color: "var(--muted)",
                      borderRadius: 6,
                      fontSize: 11,
                      padding: "5px 12px",
                      cursor: "pointer",
                    }}
                  >
                    重新上传
                  </button>
                </div>
              </div>
            ) : (
              <div
                onClick={() => fileInputRef.current?.click()}
                style={{
                  border: "2px dashed var(--border2)",
                  borderRadius: "var(--radius-sm)",
                  padding: "32px 20px",
                  textAlign: "center",
                  cursor: "pointer",
                  transition: "border-color 0.2s",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border2)")}
              >
                <div style={{ fontSize: 32, marginBottom: 8 }}>📎</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>拖放或点击上传简历</div>
                <div style={{ fontSize: 11, color: "var(--muted2)" }}>支持 PDF、DOCX 格式，上传后自动解析填充</div>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.doc"
              onChange={handleFileChange}
              style={{ display: "none" }}
            />
          </div>

          {/* Parse notice */}
          <div
            style={{
              background: "var(--blue-dim)",
              border: "1px solid var(--blue-border)",
              borderRadius: "var(--radius-sm)",
              padding: "10px 14px",
              fontSize: 12,
              color: "var(--blue)",
              marginBottom: 16,
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
            }}
          >
            <span style={{ flexShrink: 0 }}>ℹ</span>
            <span>上传简历后系统将自动解析并填充以下字段，你可以手动编辑任意内容。AI 投递时将使用此档案生成个性化打招呼语。</span>
          </div>

          {/* Basic info + Job intent grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            <div style={{ ...card, marginBottom: 0 }}>
              <div style={cardTitle}>基本信息</div>
              <span style={lbl}>姓名</span>
              <input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} />
              <span style={lbl}>邮箱</span>
              <input style={inputStyle} value={email} onChange={(e) => setEmail(e.target.value)} />
              <span style={lbl}>手机</span>
              <input style={inputStyle} value={phone} onChange={(e) => setPhone(e.target.value)} />
              <span style={lbl}>所在城市</span>
              <input style={inputStyle} value={city} onChange={(e) => setCity(e.target.value)} />
              <span style={lbl}>一句话简介</span>
              <textarea
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                placeholder="简单介绍自己…"
                rows={2}
                style={{ ...inputStyle, resize: "vertical", marginBottom: 0 }}
              />
            </div>

            <div style={{ ...card, marginBottom: 0 }}>
              <div style={cardTitle}>求职意向</div>
              <span style={lbl}>目标岗位</span>
              <input style={inputStyle} value={targetRole} onChange={(e) => setTargetRole(e.target.value)} />
              <span style={lbl}>目标城市</span>
              <input style={inputStyle} value={targetCity} onChange={(e) => setTargetCity(e.target.value)} />
              <span style={lbl}>期望薪资</span>
              <input style={inputStyle} value={salaryExpect} onChange={(e) => setSalaryExpect(e.target.value)} />
              <span style={lbl}>工作性质</span>
              <div style={{ display: "flex", gap: 6 }}>
                {["全职", "兼职", "实习", "远程"].map((t) => (
                  <button
                    key={t}
                    onClick={() => setJobType(t)}
                    style={{
                      background: jobType === t ? "var(--green-dim)" : "var(--card2)",
                      border: `1px solid ${jobType === t ? "var(--green-border)" : "var(--border)"}`,
                      color: jobType === t ? "var(--green)" : "var(--muted)",
                      borderRadius: 20,
                      fontSize: 12,
                      padding: "4px 12px",
                      cursor: "pointer",
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Skills */}
          <div style={card}>
            <div style={cardTitle}>技能标签</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
              {skills.map((s) => (
                <span
                  key={s}
                  style={{
                    background: "var(--blue-dim)",
                    color: "var(--blue)",
                    border: "1px solid var(--blue-border)",
                    borderRadius: 20,
                    fontSize: 12,
                    fontWeight: 500,
                    padding: "4px 12px",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  {s}
                  <button
                    onClick={() => removeSkill(s)}
                    style={{ background: "none", border: "none", color: "var(--blue)", cursor: "pointer", fontSize: 13, padding: 0, lineHeight: 1 }}
                  >
                    ×
                  </button>
                </span>
              ))}
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  value={newSkill}
                  onChange={(e) => setNewSkill(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addSkill(); } }}
                  placeholder="+ 添加技能"
                  style={{
                    background: "var(--card2)",
                    border: "1px dashed var(--border2)",
                    borderRadius: 20,
                    color: "var(--muted)",
                    fontSize: 12,
                    padding: "4px 12px",
                    outline: "none",
                    width: 100,
                  }}
                />
                <button
                  onClick={addSkill}
                  style={{
                    background: "var(--green-dim)",
                    border: "1px solid var(--green-border)",
                    color: "var(--green)",
                    borderRadius: 20,
                    fontSize: 12,
                    padding: "4px 12px",
                    cursor: "pointer",
                  }}
                >
                  添加
                </button>
              </div>
            </div>
          </div>

          {/* Work experience */}
          <div style={card}>
            <div style={cardTitle}>
              <span>工作经历</span>
              <button
                onClick={() => setEditingExp({ idx: -1, item: { ...BLANK_EXP } })}
                style={{ background: "var(--accent-dim)", border: "1px solid var(--accent-border)", color: "var(--accent)", borderRadius: 8, fontSize: 12, fontWeight: 600, padding: "4px 12px", cursor: "pointer" }}
              >
                + 添加
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {experiences.map((exp, i) => (
                <div
                  key={i}
                  style={{
                    background: "var(--card2)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "14px 16px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, alignItems: "flex-start" }}>
                    <div>
                      <span style={{ fontSize: 13, fontWeight: 700 }}>{exp.company}</span>
                      <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 8 }}>{exp.role}</span>
                    </div>
                    <div style={{ display: "flex", gap: 4, alignItems: "center", flexShrink: 0 }}>
                      <span style={{ fontSize: 11, color: "var(--muted2)", marginRight: 6 }}>{exp.duration}</span>
                      <button onClick={() => setEditingExp({ idx: i, item: exp })} style={iconBtn("var(--blue)")}>编辑</button>
                      <button
                        onClick={() => setExperiences((prev) => prev.filter((_, j) => j !== i))}
                        style={iconBtn("var(--red)")}
                      >
                        删除
                      </button>
                    </div>
                  </div>
                  <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                    {exp.bullets.map((b, j) => (
                      <li
                        key={j}
                        style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6, paddingLeft: 14, position: "relative", marginBottom: 2 }}
                      >
                        <span style={{ position: "absolute", left: 0, top: 7, width: 5, height: 5, borderRadius: "50%", background: "var(--green)", opacity: 0.6 }} />
                        {b}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {experiences.length === 0 && (
                <div style={{ textAlign: "center", color: "var(--muted2)", fontSize: 13, padding: "20px 0" }}>暂无工作经历，点击"+ 添加"</div>
              )}
            </div>
          </div>

          {/* Projects */}
          <div style={card}>
            <div style={cardTitle}>
              <span>项目经历</span>
              <button
                onClick={() => setEditingProj({ idx: -1, item: { ...BLANK_PROJ } })}
                style={{ background: "var(--accent-dim)", border: "1px solid var(--accent-border)", color: "var(--accent)", borderRadius: 8, fontSize: 12, fontWeight: 600, padding: "4px 12px", cursor: "pointer" }}
              >
                + 添加
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {projects.map((proj, i) => (
                <div
                  key={i}
                  style={{
                    background: "var(--card2)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "14px 16px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, alignItems: "flex-start" }}>
                    <span style={{ fontSize: 13, fontWeight: 700 }}>{proj.name}</span>
                    <div style={{ display: "flex", gap: 4, alignItems: "center", flexShrink: 0 }}>
                      {proj.github && (
                        <a href={proj.github} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: "var(--blue)", textDecoration: "none", marginRight: 6 }}>
                          GitHub ↗
                        </a>
                      )}
                      <button onClick={() => setEditingProj({ idx: i, item: proj })} style={iconBtn("var(--blue)")}>编辑</button>
                      <button
                        onClick={() => setProjects((prev) => prev.filter((_, j) => j !== i))}
                        style={iconBtn("var(--red)")}
                      >
                        删除
                      </button>
                    </div>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 8 }}>
                    {proj.tech.split("·").map((t) => (
                      <span
                        key={t.trim()}
                        style={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 4, fontSize: 10, padding: "2px 8px", color: "var(--muted2)" }}
                      >
                        {t.trim()}
                      </span>
                    ))}
                  </div>
                  <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                    {proj.bullets.map((b, j) => (
                      <li
                        key={j}
                        style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6, paddingLeft: 14, position: "relative", marginBottom: 2 }}
                      >
                        <span style={{ position: "absolute", left: 0, top: 7, width: 5, height: 5, borderRadius: "50%", background: "var(--blue)", opacity: 0.6 }} />
                        {b}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              {projects.length === 0 && (
                <div style={{ textAlign: "center", color: "var(--muted2)", fontSize: 13, padding: "20px 0" }}>暂无项目经历，点击"+ 添加"</div>
              )}
            </div>
          </div>

          {/* Save bar */}
          <div
            style={{
              position: "sticky",
              bottom: 0,
              background: "var(--bg)",
              borderTop: "1px solid var(--border)",
              padding: "14px 0",
              display: "flex",
              gap: 10,
              alignItems: "center",
            }}
          >
            <button
              onClick={handleSave}
              style={{
                background: "var(--accent)",
                color: "#fff",
                border: "none",
                borderRadius: "var(--radius-sm)",
                fontSize: 13,
                fontWeight: 700,
                padding: "10px 24px",
                cursor: "pointer",
              }}
            >
              {saved ? "✓ 已保存" : "保存档案"}
            </button>
            {saved && (
              <span style={{ fontSize: 12, color: "var(--green, #10b981)", fontWeight: 500 }}>
                ✓ 档案已保存
              </span>
            )}
            {saveError && (
              <span style={{ fontSize: 12, color: "var(--red, #ef4444)", fontWeight: 500 }}>
                ⚠ {saveError}
              </span>
            )}
            <button
              onClick={() => fileInputRef.current?.click()}
              style={{
                background: "transparent",
                border: "1px solid var(--border2)",
                color: "var(--muted)",
                borderRadius: "var(--radius-sm)",
                fontSize: 13,
                fontWeight: 500,
                padding: "10px 20px",
                cursor: "pointer",
              }}
            >
              重新上传简历
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
