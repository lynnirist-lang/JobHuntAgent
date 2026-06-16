"use client";

import { useState, useEffect, useCallback } from "react";

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
};

const label: React.CSSProperties = {
  fontSize: 12,
  color: "var(--muted)",
  marginBottom: 6,
  display: "block",
};

function RangeRow({
  label: lbl,
  value,
  min,
  max,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  unit: string;
  onChange: (v: number) => void;
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{lbl}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--fg)" }}>
          {value} {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: "var(--green)", cursor: "pointer" }}
      />
    </div>
  );
}

function Checkbox({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        cursor: "pointer",
        fontSize: 13,
        color: "var(--fg)",
        marginBottom: 8,
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ accentColor: "var(--green)", width: 14, height: 14, cursor: "pointer" }}
      />
      {children}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  background: "var(--card2)",
  border: "1px solid var(--border2)",
  borderRadius: "var(--radius-sm)",
  color: "var(--fg)",
  fontSize: 13,
  padding: "8px 12px",
  outline: "none",
  width: "100%",
};

export default function SettingsPage() {
  // ── 登录状态 ──────────────────────────────────────────────────────
  const [loginStatus, setLoginStatus] = useState<{ logged_in: boolean; message: string } | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);

  const fetchLoginStatus = useCallback(() => {
    fetch("/api/auth/check", { method: "POST" })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d) setLoginStatus(d); })
      .catch(() => {});
  }, []);

  useEffect(() => { fetchLoginStatus(); }, [fetchLoginStatus]);

  const handleLogin = async () => {
    setLoginLoading(true);
    try {
      await fetch("/api/auth/login", { method: "POST" });
      // 轮询等待登录完成（扫码需要时间）
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const res = await fetch("/api/auth/status");
        if (res.ok) {
          const d = await res.json();
          setLoginStatus(d);
          if (d.logged_in) break;
        }
      }
    } finally {
      setLoginLoading(false);
      fetchLoginStatus();
    }
  };

  const handleLogout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    fetchLoginStatus();
  };

  const [mode, setMode] = useState<"scheduled" | "manual">("scheduled");
  const [cooldown, setCooldown] = useState(30);
  const [dailyLimit, setDailyLimit] = useState(30);
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("22:00");
  const [interval, setInterval2] = useState(60);
  const [maxPages, setMaxPages] = useState(3);
  const [captchaStrategy, setCaptchaStrategy] = useState("pause");
  const [failStrategy, setFailStrategy] = useState("retry");

  // Greeting config
  const [tone, setTone] = useState("专业");
  const [wordCount, setWordCount] = useState(120);
  const [greetingSuffix, setGreetingSuffix] = useState("");
  const [greetingExtra, setGreetingExtra] = useState("");
  const [includeSkills, setIncludeSkills] = useState(true);
  const [includeExperience, setIncludeExperience] = useState(true);
  const [includeProject, setIncludeProject] = useState(false);

  // Resume prefs
  const [adaptHighlight, setAdaptHighlight] = useState(true);
  const [adaptTone, setAdaptTone] = useState(true);
  const [avoidWords, setAvoidWords] = useState("");
  const [resumeExtra, setResumeExtra] = useState("");

  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Holds the full raw settings from backend so non-UI fields (e.g. delay_mean) are preserved on save
  const [rawSettings, setRawSettings] = useState<Record<string, unknown>>({});

  // Load persisted settings on mount
  useEffect(() => {
    fetch("/api/settings")
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (!data) return;
        setRawSettings(data);
        if (data.mode)                          setMode(data.mode);
        if (data.cooldown_minutes != null)      setCooldown(data.cooldown_minutes);
        if (data.start_time)                    setStartTime(data.start_time);
        if (data.end_time)                      setEndTime(data.end_time);
        if (data.auto_interval_minutes != null) setInterval2(data.auto_interval_minutes);
        if (data.max_pages != null)             setMaxPages(data.max_pages);
        if (data.captcha_strategy)              setCaptchaStrategy(data.captcha_strategy);
        if (data.fail_strategy)                 setFailStrategy(data.fail_strategy);
        if (data.apply?.daily_limit != null)    setDailyLimit(data.apply.daily_limit);
        if (data.greeting) {
          const g = data.greeting;
          if (g.tone)                    setTone(g.tone);
          if (g.word_count)              setWordCount(g.word_count);
          if (g.suffix != null)          setGreetingSuffix(g.suffix);
          if (g.extra_instruction != null) setGreetingExtra(g.extra_instruction);
          if (g.include_skills != null)    setIncludeSkills(g.include_skills);
          if (g.include_experience != null) setIncludeExperience(g.include_experience);
          if (g.include_project != null)   setIncludeProject(g.include_project);
        }
        if (data.resume_adapt) {
          const r = data.resume_adapt;
          if (r.highlight_keywords != null) setAdaptHighlight(r.highlight_keywords);
          if (r.adapt_tone != null)         setAdaptTone(r.adapt_tone);
          if (Array.isArray(r.avoid_words)) setAvoidWords(r.avoid_words.join("\n"));
          if (r.extra_instruction != null)  setResumeExtra(r.extra_instruction);
        }
      })
      .catch(() => {/* backend may not be running */});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async () => {
    setSaveError(null);
    const rawApply = (rawSettings.apply as Record<string, unknown>) || {};
    const rawGreeting = (rawSettings.greeting as Record<string, unknown>) || {};
    const rawResumeAdapt = (rawSettings.resume_adapt as Record<string, unknown>) || {};
    const body = {
      settings: {
        ...rawSettings,           // preserve all non-UI fields (score, search, etc.)
        mode,
        cooldown_minutes: cooldown,
        start_time: startTime,
        end_time: endTime,
        auto_interval_minutes: interval,
        max_pages: maxPages,
        captcha_strategy: captchaStrategy,
        fail_strategy: failStrategy,
        apply: {
          ...rawApply,            // preserve delay_mean / delay_std / delay_min / consecutive_fail_limit
          daily_limit: dailyLimit,
        },
        greeting: {
          ...rawGreeting,
          tone,
          word_count: wordCount,
          suffix: greetingSuffix,
          extra_instruction: greetingExtra,
          include_skills: includeSkills,
          include_experience: includeExperience,
          include_project: includeProject,
        },
        resume_adapt: {
          ...rawResumeAdapt,
          highlight_keywords: adaptHighlight,
          adapt_tone: adaptTone,
          avoid_words: avoidWords.split("\n").map((w) => w.trim()).filter(Boolean),
          extra_instruction: resumeExtra,
        },
      },
    };
    try {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`保存失败 (${res.status})`);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleReset = () => {
    setMode("scheduled");
    setCooldown(30);
    setDailyLimit(30);
    setStartTime("09:00");
    setEndTime("22:00");
    setInterval2(60);
    setMaxPages(3);
  };

  const tones = ["专业", "热情", "简洁", "创意"];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
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
        <span style={{ fontWeight: 700, fontSize: 15 }}>策略配置</span>
      </header>

      {/* Content */}
      <div style={{ padding: "20px", overflowY: "auto", height: "calc(100vh - var(--topbar-h))" }}>
        <div style={{ maxWidth: 640 }}>

          {/* BOSS 直聘登录状态 */}
          <div style={card}>
            <div style={cardTitle}>BOSS 直聘账号</div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span
                  style={{
                    width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
                    background: loginStatus?.logged_in ? "#10B981" : "#F43F5E",
                    boxShadow: loginStatus?.logged_in ? "0 0 6px rgba(16,185,129,0.6)" : "0 0 6px rgba(244,63,94,0.5)",
                  }}
                />
                <span style={{ fontSize: 13, color: "var(--fg)", fontWeight: 600 }}>
                  {loginStatus
                    ? loginStatus.logged_in ? "已登录" : "未登录 / 会话已过期"
                    : "检测中…"}
                </span>
                {loginStatus?.message && (
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>{loginStatus.message}</span>
                )}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={handleLogin}
                  disabled={loginLoading}
                  style={{
                    background: "#3B82F6", color: "#fff", border: "none",
                    borderRadius: 8, fontSize: 12, fontWeight: 700,
                    padding: "8px 16px", cursor: loginLoading ? "wait" : "pointer",
                    opacity: loginLoading ? 0.7 : 1,
                  }}
                >
                  {loginLoading ? "等待扫码…" : loginStatus?.logged_in ? "重新登录" : "扫码登录"}
                </button>
                {loginStatus?.logged_in && (
                  <button
                    onClick={handleLogout}
                    style={{
                      background: "transparent", color: "var(--muted)",
                      border: "1px solid var(--border2)", borderRadius: 8,
                      fontSize: 12, fontWeight: 600, padding: "8px 14px", cursor: "pointer",
                    }}
                  >
                    退出
                  </button>
                )}
              </div>
            </div>
            {loginLoading && (
              <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 10 }}>
                BOSS 直聘扫码窗口已在后台打开，请在浏览器中完成扫码（最多等待 2 分钟）…
              </p>
            )}
          </div>

          {/* 执行模式 */}
          <div style={card}>
            <div style={cardTitle}>执行模式</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {([
                { value: "scheduled", icon: "⏰", title: "定时自动", desc: "按计划自动运行" },
                { value: "manual",    icon: "🖱",  title: "手动触发", desc: "每次手动启动"   },
              ] as const).map(({ value, icon, title, desc }) => (
                <button
                  key={value}
                  onClick={() => setMode(value)}
                  style={{
                    background: mode === value ? "var(--green-dim)" : "var(--card2)",
                    border: `1px solid ${mode === value ? "var(--green-border)" : "var(--border)"}`,
                    borderRadius: "var(--radius-sm)",
                    padding: "14px 16px",
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ fontSize: 20, marginBottom: 6 }}>{icon}</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: mode === value ? "var(--green)" : "var(--fg)", marginBottom: 3 }}>
                    {title}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted2)" }}>{desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 冷却期 */}
          <div style={card}>
            <div style={cardTitle}>冷却期设置</div>
            <RangeRow label="两次投递间隔" value={cooldown} min={0} max={120} unit="分钟" onChange={setCooldown} />
          </div>

          {/* 运行限制 */}
          <div style={card}>
            <div style={cardTitle}>运行限制</div>
            <RangeRow label="每日最大投递量" value={dailyLimit} min={1} max={50} unit="次" onChange={setDailyLimit} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
              <div>
                <span style={label}>开始时间</span>
                <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} style={inputStyle} />
              </div>
              <div>
                <span style={label}>结束时间</span>
                <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} style={inputStyle} />
              </div>
            </div>
            <RangeRow label="自动运行间隔" value={interval} min={10} max={360} unit="分钟" onChange={setInterval2} />
          </div>

          {/* 异常处理 */}
          <div style={card}>
            <div style={cardTitle}>异常处理</div>
            <div style={{ marginBottom: 14 }}>
              <span style={label}>遇到验证码时</span>
              <div style={{ display: "flex", gap: 8 }}>
                {[
                  { v: "pause",  l: "暂停等待" },
                  { v: "skip",   l: "跳过此次" },
                  { v: "notify", l: "通知我"   },
                ].map(({ v, l }) => (
                  <label key={v} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 12, color: captchaStrategy === v ? "var(--green)" : "var(--muted)" }}>
                    <input type="radio" value={v} checked={captchaStrategy === v} onChange={() => setCaptchaStrategy(v)} style={{ accentColor: "var(--green)" }} />
                    {l}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <span style={label}>投递失败时</span>
              <div style={{ display: "flex", gap: 8 }}>
                {[
                  { v: "retry", l: "自动重试" },
                  { v: "skip",  l: "标记失败" },
                  { v: "stop",  l: "停止任务" },
                ].map(({ v, l }) => (
                  <label key={v} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 12, color: failStrategy === v ? "var(--green)" : "var(--muted)" }}>
                    <input type="radio" value={v} checked={failStrategy === v} onChange={() => setFailStrategy(v)} style={{ accentColor: "var(--green)" }} />
                    {l}
                  </label>
                ))}
              </div>
            </div>
          </div>

          {/* 每页爬取 */}
          <div style={card}>
            <div style={cardTitle}>爬取设置</div>
            <RangeRow label="每次爬取页数" value={maxPages} min={1} max={10} unit="页" onChange={setMaxPages} />
          </div>

          {/* 打招呼配置 */}
          <div style={card}>
            <div style={cardTitle}>打招呼配置</div>

            <div style={{ marginBottom: 14 }}>
              <span style={label}>语气风格</span>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {tones.map((t) => (
                  <button
                    key={t}
                    onClick={() => setTone(t)}
                    style={{
                      background: tone === t ? "var(--green-dim)" : "var(--card2)",
                      border: `1px solid ${tone === t ? "var(--green-border)" : "var(--border)"}`,
                      color: tone === t ? "var(--green)" : "var(--muted)",
                      borderRadius: 20,
                      fontSize: 12,
                      fontWeight: tone === t ? 600 : 500,
                      padding: "5px 14px",
                      cursor: "pointer",
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ marginBottom: 14 }}>
              <span style={label}>内容包含</span>
              <Checkbox checked={includeSkills} onChange={setIncludeSkills}>突出技能匹配</Checkbox>
              <Checkbox checked={includeExperience} onChange={setIncludeExperience}>提及相关经历</Checkbox>
              <Checkbox checked={includeProject} onChange={setIncludeProject}>引用项目案例</Checkbox>
            </div>

            <RangeRow label="字数控制" value={wordCount} min={80} max={200} unit="字" onChange={setWordCount} />

            <div style={{ marginBottom: 14 }}>
              <span style={label}>结尾附言</span>
              <input
                type="text"
                value={greetingSuffix}
                onChange={(e) => setGreetingSuffix(e.target.value)}
                placeholder="例：期待与您进一步交流！"
                style={inputStyle}
              />
            </div>

            <div style={{ marginBottom: 14 }}>
              <span style={label}>额外指令</span>
              <textarea
                value={greetingExtra}
                onChange={(e) => setGreetingExtra(e.target.value)}
                placeholder="给 AI 的额外生成指令…"
                rows={3}
                style={{ ...inputStyle, resize: "vertical" }}
              />
            </div>

            {/* Tip */}
            <div
              style={{
                background: "rgba(59,130,246,0.06)",
                border: "1px solid rgba(59,130,246,0.18)",
                borderRadius: "var(--radius-sm)",
                padding: "10px 14px",
                fontSize: 12,
                color: "var(--muted)",
                lineHeight: 1.6,
              }}
            >
              <strong style={{ color: "var(--fg)" }}>配置生效说明：</strong>
              保存后，下次爬取时会用新配置生成打招呼语。
              若要对<strong>已有岗位</strong>应用新配置，请回到主页点击「重新生成打招呼」按钮。
              {greetingSuffix && (
                <span>附言「{greetingSuffix}」将追加到每条打招呼末尾。</span>
              )}
            </div>
          </div>

          {/* 简历适配偏好 */}
          <div style={card}>
            <div style={cardTitle}>简历适配偏好</div>
            <Checkbox checked={adaptHighlight} onChange={setAdaptHighlight}>突出与 JD 匹配的关键词</Checkbox>
            <Checkbox checked={adaptTone} onChange={setAdaptTone}>调整措辞风格贴合岗位</Checkbox>

            <div style={{ marginBottom: 14, marginTop: 8 }}>
              <span style={label}>避免出现的词汇</span>
              <textarea
                value={avoidWords}
                onChange={(e) => setAvoidWords(e.target.value)}
                placeholder="每行一个词…"
                rows={3}
                style={{ ...inputStyle, resize: "vertical" }}
              />
            </div>

            <div>
              <span style={label}>额外指令</span>
              <textarea
                value={resumeExtra}
                onChange={(e) => setResumeExtra(e.target.value)}
                placeholder="给 AI 的额外简历适配指令…"
                rows={3}
                style={{ ...inputStyle, resize: "vertical" }}
              />
            </div>
          </div>

          {/* 投递机制说明 */}
          <div style={card}>
            <div style={cardTitle}>投递机制说明</div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 0, overflowX: "auto", paddingBottom: 8 }}>
              {[
                { icon: "🔍", step: "爬取岗位", desc: "按关键词抓取" },
                { icon: "🤖", step: "AI 分析",  desc: "评分 & 生成招呼" },
                { icon: "✅", step: "人工审批",  desc: "你决定批准" },
                { icon: "📤", step: "自动发送",  desc: "自动投递" },
                { icon: "📊", step: "状态追踪",  desc: "实时同步结果" },
              ].map(({ icon, step, desc }, i, arr) => (
                <div key={step} style={{ display: "flex", alignItems: "center" }}>
                  <div style={{ textAlign: "center", minWidth: 80 }}>
                    <div style={{ fontSize: 22, marginBottom: 4 }}>{icon}</div>
                    <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 2 }}>{step}</div>
                    <div style={{ fontSize: 10, color: "var(--muted2)" }}>{desc}</div>
                  </div>
                  {i < arr.length - 1 && (
                    <div style={{ fontSize: 16, color: "var(--muted2)", padding: "0 6px", marginBottom: 20 }}>→</div>
                  )}
                </div>
              ))}
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
              {saved ? "✓ 已保存" : "保存配置"}
            </button>
            <button
              onClick={handleReset}
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
              恢复默认
            </button>
            {saved && (
              <span style={{ fontSize: 12, color: "var(--green, #10b981)", fontWeight: 500 }}>
                ✓ 配置已保存
              </span>
            )}
            {saveError && (
              <span style={{ fontSize: 12, color: "var(--red)", fontWeight: 500 }}>
                ⚠ {saveError}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
