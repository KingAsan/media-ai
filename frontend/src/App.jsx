import { useCallback, useEffect, useRef, useState } from 'react';
import { marked } from 'marked';

const FAVORITES_KEY = 'favorites';
const THEME_KEY = 'media-ai-theme';
const DOWNLOAD_URL = 'https://github.com/KingAsan/media-ai/releases/download/media/media.exe';

const THEMES = [
  ['', 'Netflix Red', '#ff4b4b'],
  ['theme-blue', 'Cyber Blue', '#00f2ff'],
  ['theme-purple', 'Magic Purple', '#d946ef'],
  ['theme-green', 'Matrix Green', '#00ff41'],
  ['theme-gold', 'Luxury Gold', '#fbbf24'],
  ['theme-anime', 'Anime Vibe', '#ff6ec7']
];

const QUICK = [
  ['ri-movie-2-line', 'Посоветуй фильм в жанре киберпанк'],
  ['ri-gamepad-line', 'Игра для компании друзей на ПК'],
  ['ri-headphone-line', 'Музыка для программирования без слов'],
  ['ri-tv-line', 'Сериал с сильным сюжетом на вечер']
];

const MODES = [
  ['balanced', 'Сбалансированный'],
  ['fast', 'Быстрый'],
  ['deep', 'Глубокий'],
  ['surprise', 'Сюрприз']
];

const RATINGS = [
  ['any', 'Любой'],
  ['family', 'Семейный'],
  ['teen', 'Подростковый'],
  ['adult', '18+']
];

const LANGS = [
  ['ru', 'Русский'],
  ['en', 'English'],
  ['any', 'Любой']
];

const genId = () => `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const genSession = () =>
  (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

const splitCsv = (v) => String(v || '')
  .split(',')
  .map((x) => x.trim())
  .filter(Boolean)
  .slice(0, 12);

const parse = (v, d) => {
  try {
    const r = JSON.parse(v || '');
    return r ?? d;
  } catch {
    return d;
  }
};

const escapeRegExp = (v) => String(v || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const autoHighlightDescription = (description, title = '') => {
  let out = String(description || '').trim();
  const source = out;
  if (!out) return '';
  if (/(\*\*|__|<strong>|<b>)/i.test(out)) return out;

  out = out
    .replace(/«([^»\n]{2,120})»/g, (_, p1) => `**«${p1}»**`)
    .replace(/"([^"\n]{2,120})"/g, (_, p1) => `**"${p1}"**`)
    .replace(/“([^”\n]{2,120})”/g, (_, p1) => `**“${p1}”**`);

  const cleanTitle = String(title || '').trim();
  if (cleanTitle.length > 1) {
    const quotedTitleRe = new RegExp(`[«"“]\\s*${escapeRegExp(cleanTitle)}\\s*[»"”]`, 'i');
    if (!quotedTitleRe.test(source)) {
      const titleRe = new RegExp(escapeRegExp(cleanTitle), 'gi');
      out = out.replace(titleRe, (m) => `**${m}**`);
    }
  }

  return out;
};

const formatSessionTime = (value) => {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

const isGameRecommendation = (item, requestText = '') => {
  const category = String(item?.category || '').toLowerCase();
  const yearGenre = String(item?.year_genre || '').toLowerCase();
  const request = String(requestText || '').toLowerCase();
  const text = `${category} ${yearGenre} ${request}`;
  return /игр|game|steam|pc|xbox|ps5|playstation|nintendo/.test(text);
};

const steamSearchUrl = (title) =>
  `https://store.steampowered.com/search/?term=${encodeURIComponent(String(title || '').trim())}`;

marked.setOptions({ gfm: true, breaks: true });

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('access_token') || '');
  const [user, setUser] = useState(localStorage.getItem('username') || '');
  const [isAdmin, setIsAdmin] = useState(localStorage.getItem('is_admin') === 'true');
  const [isRegister, setIsRegister] = useState(false);
  const [loginUser, setLoginUser] = useState('');
  const [loginPass, setLoginPass] = useState('');

  const [theme, setTheme] = useState(localStorage.getItem(THEME_KEY) || '');
  const [themeOpen, setThemeOpen] = useState(false);
  const [drawer, setDrawer] = useState(false);

  const [sessionId, setSessionId] = useState(localStorage.getItem('currentSessionId') || genSession());
  const [input, setInput] = useState('');
  const [started, setStarted] = useState(false);
  const [tempMode, setTempMode] = useState(false);
  const [messages, setMessages] = useState([]);
  const [activeVideo, setActiveVideo] = useState({});
  const [feedbackState, setFeedbackState] = useState({});

  const [sessions, setSessions] = useState([]);
  const [sessionsState, setSessionsState] = useState('');
  const [favorites, setFavorites] = useState(() => parse(localStorage.getItem(FAVORITES_KEY), []));

  const [prefs, setPrefs] = useState({
    favorite_categories: '',
    disliked_categories: '',
    favorite_platforms: '',
    preferred_language: 'ru',
    age_rating: 'any',
    discovery_mode: 'balanced'
  });
  const [savingPrefs, setSavingPrefs] = useState(false);

  const [ctx, setCtx] = useState({ assistant_mode: 'balanced', mood: '', company: '', time_minutes: '' });
  const [insights, setInsights] = useState({
    total_queries: 0,
    total_sessions: 0,
    favorite_category: 'Not enough data',
    top_categories: []
  });

  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [savingOnboarding, setSavingOnboarding] = useState(false);
  const [onboarding, setOnboarding] = useState({
    favorite_categories: '',
    disliked_categories: '',
    favorite_platforms: '',
    preferred_language: 'ru',
    discovery_mode: 'balanced'
  });

  const [adminOpen, setAdminOpen] = useState(false);
  const [adminTab, setAdminTab] = useState('stats');
  const [adminBusy, setAdminBusy] = useState(false);
  const [adminStats, setAdminStats] = useState(null);
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminRules, setAdminRules] = useState([]);
  const [adminPinned, setAdminPinned] = useState([]);
  const [adminSettings, setAdminSettings] = useState({
    force_lite_mode: false,
    default_daily_limit: 40
  });
  const [adminRuleForm, setAdminRuleForm] = useState({
    title: '',
    category: '',
    rule_type: 'blacklist',
    notes: ''
  });
  const [adminPinnedForm, setAdminPinnedForm] = useState({
    title: '',
    year_genre: '',
    description: '',
    category: '',
    why_this: '',
    video_id: '',
    is_active: true
  });

  const [toasts, setToasts] = useState([]);
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [deferred, setDeferred] = useState(null);

  const streamRef = useRef(null);
  const dropdownRef = useRef(null);
  const themeBtnRef = useRef(null);

  const toast = useCallback((text, type = 'success') => {
    const id = genId();
    setToasts((p) => [...p, { id, text, type }]);
    setTimeout(() => setToasts((p) => p.filter((t) => t.id !== id)), 2600);
  }, []);

  const authFetch = useCallback(
    (url, options = {}) => fetch(url, {
      ...options,
      headers: {
        ...(options.headers || {}),
        Authorization: `Bearer ${token}`
      }
    }),
    [token]
  );

  useEffect(() => {
    document.body.className = '';
    if (theme) document.body.classList.add(theme);
    if (token) document.body.classList.add('logged-in');
    if (started) document.body.classList.add('chat-active');
  }, [theme, token, started]);

  useEffect(() => localStorage.setItem(THEME_KEY, theme), [theme]);
  useEffect(() => localStorage.setItem('currentSessionId', sessionId), [sessionId]);
  useEffect(() => localStorage.setItem(FAVORITES_KEY, JSON.stringify(favorites.slice(0, 25))), [favorites]);

  useEffect(() => {
    const online = () => setIsOnline(true);
    const offline = () => setIsOnline(false);
    window.addEventListener('online', online);
    window.addEventListener('offline', offline);
    return () => {
      window.removeEventListener('online', online);
      window.removeEventListener('offline', offline);
    };
  }, []);

  useEffect(() => {
    const click = (e) => {
      const insideDrop = dropdownRef.current?.contains(e.target);
      const insideBtn = themeBtnRef.current?.contains(e.target);
      if (themeOpen && !insideDrop && !insideBtn) setThemeOpen(false);
    };
    document.addEventListener('click', click);
    return () => document.removeEventListener('click', click);
  }, [themeOpen]);

  useEffect(() => {
    if (!drawer) return;
    const onEsc = (e) => {
      if (e.key === 'Escape') setDrawer(false);
    };
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [drawer]);

  useEffect(() => {
    if (!streamRef.current) return;
    requestAnimationFrame(() => {
      if (streamRef.current) streamRef.current.scrollTop = streamRef.current.scrollHeight;
    });
  }, [messages]);

  useEffect(() => {
    const onPrompt = (e) => {
      e.preventDefault();
      setDeferred(e);
    };
    const onInstalled = () => {
      setDeferred(null);
      toast('PWA успешно установлен');
    };
    window.addEventListener('beforeinstallprompt', onPrompt);
    window.addEventListener('appinstalled', onInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt);
      window.removeEventListener('appinstalled', onInstalled);
    };
  }, [toast]);

  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js').catch(() => {});
    });
  }, []);

  const logout = useCallback(() => {
    ['access_token', 'username', 'is_admin', 'currentSessionId'].forEach((k) => localStorage.removeItem(k));
    setToken('');
    setUser('');
    setIsAdmin(false);
    setMessages([]);
    setSessions([]);
    setStarted(false);
    setInput('');
    setSessionId(genSession());
    setDrawer(false);
    setOnboardingOpen(false);
  }, []);

  const loadSessions = useCallback(async () => {
    if (!token) return setSessionsState('Войди, чтобы увидеть историю');
    setSessionsState('Загрузка...');
    try {
      const r = await authFetch('/api/sessions');
      if (r.status === 401) return logout();
      const d = await r.json();
      const normalized = Array.isArray(d) ? d.map((s) => ({
        session_id: s.session_id,
        title: s.title || 'Новый чат',
        preview: s.preview || '',
        message_count: Number(s.message_count || 0),
        last_timestamp: s.last_timestamp || null
      })) : [];
      setSessions(normalized);
      setSessionsState(normalized.length ? '' : 'История пуста');
    } catch {
      setSessionsState('Ошибка загрузки');
    }
  }, [authFetch, logout, token]);

  const loadPrefs = useCallback(async () => {
    if (!token) return;
    try {
      const r = await authFetch('/api/preferences');
      if (r.status === 401) return logout();
      const d = await r.json();
      const next = {
        favorite_categories: (d.favorite_categories || []).join(', '),
        disliked_categories: (d.disliked_categories || []).join(', '),
        favorite_platforms: (d.favorite_platforms || []).join(', '),
        preferred_language: d.preferred_language || 'ru',
        age_rating: d.age_rating || 'any',
        discovery_mode: d.discovery_mode || 'balanced'
      };
      setPrefs(next);
      setCtx((p) => ({ ...p, assistant_mode: next.discovery_mode }));
      setOnboarding((prev) => ({
        ...prev,
        favorite_categories: next.favorite_categories,
        disliked_categories: next.disliked_categories,
        favorite_platforms: next.favorite_platforms,
        preferred_language: next.preferred_language,
        discovery_mode: next.discovery_mode
      }));
    } catch {}
  }, [authFetch, logout, token]);

  const loadInsights = useCallback(async () => {
    if (!token) return;
    try {
      const r = await authFetch('/api/insights');
      if (r.status === 401) return logout();
      const d = await r.json();
      setInsights({
        total_queries: Number(d.total_queries || 0),
        total_sessions: Number(d.total_sessions || 0),
        favorite_category: d.favorite_category || 'Not enough data',
        top_categories: Array.isArray(d.top_categories) ? d.top_categories : []
      });
    } catch {}
  }, [authFetch, logout, token]);

  const loadOnboardingStatus = useCallback(async () => {
    if (!token) return;
    try {
      const r = await authFetch('/api/onboarding/status');
      if (r.status === 401) return logout();
      const d = await r.json();
      setOnboardingOpen(!Boolean(d.completed));
    } catch {}
  }, [authFetch, logout, token]);

  const loadAdminData = useCallback(async () => {
    if (!token || !isAdmin) return;
    setAdminBusy(true);
    try {
      const [
        statsRes,
        usersRes,
        rulesRes,
        pinnedRes,
        settingsRes
      ] = await Promise.all([
        authFetch('/api/admin/stats'),
        authFetch('/api/admin/users'),
        authFetch('/api/admin/content-rules'),
        authFetch('/api/admin/pinned'),
        authFetch('/api/admin/settings')
      ]);

      if ([statsRes, usersRes, rulesRes, pinnedRes, settingsRes].some((r) => r.status === 401)) {
        return logout();
      }
      if ([statsRes, usersRes, rulesRes, pinnedRes, settingsRes].some((r) => r.status === 403)) {
        toast('Недостаточно прав администратора', 'error');
        return;
      }

      const [stats, users, rules, pinned, settings] = await Promise.all([
        statsRes.json(),
        usersRes.json(),
        rulesRes.json(),
        pinnedRes.json(),
        settingsRes.json()
      ]);

      setAdminStats(stats || null);
      setAdminUsers(Array.isArray(users) ? users : []);
      setAdminRules(Array.isArray(rules) ? rules : []);
      setAdminPinned(Array.isArray(pinned) ? pinned : []);
      setAdminSettings({
        force_lite_mode: Boolean(settings?.force_lite_mode),
        default_daily_limit: Number(settings?.default_daily_limit || 40)
      });
    } catch {
      toast('Не удалось загрузить админ-панель', 'error');
    } finally {
      setAdminBusy(false);
    }
  }, [authFetch, isAdmin, logout, toast, token]);

  const saveAdminSettings = useCallback(async () => {
    if (!token || !isAdmin) return;
    try {
      const r = await authFetch('/api/admin/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          force_lite_mode: Boolean(adminSettings.force_lite_mode),
          default_daily_limit: Number(adminSettings.default_daily_limit || 40)
        })
      });
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('settings');
      toast('Админ-настройки сохранены');
      loadAdminData();
    } catch {
      toast('Не удалось сохранить админ-настройки', 'error');
    }
  }, [adminSettings.default_daily_limit, adminSettings.force_lite_mode, authFetch, isAdmin, loadAdminData, logout, toast, token]);

  const updateAdminUser = useCallback(async (id, patch) => {
    if (!token || !isAdmin) return;
    try {
      const r = await authFetch(`/api/admin/users/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch)
      });
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('user update');
      toast('Пользователь обновлен');
      loadAdminData();
    } catch {
      toast('Не удалось обновить пользователя', 'error');
    }
  }, [authFetch, isAdmin, loadAdminData, logout, toast, token]);

  const resetUserHistory = useCallback(async (id) => {
    if (!token || !isAdmin) return;
    try {
      const r = await authFetch(`/api/admin/users/${id}/history`, { method: 'DELETE' });
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('reset');
      toast('История пользователя очищена');
      loadAdminData();
      loadInsights();
      loadSessions();
    } catch {
      toast('Не удалось очистить историю', 'error');
    }
  }, [authFetch, isAdmin, loadAdminData, loadInsights, loadSessions, logout, toast, token]);

  const createAdminRule = useCallback(async () => {
    if (!token || !isAdmin) return;
    try {
      const r = await authFetch('/api/admin/content-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(adminRuleForm)
      });
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('rule');
      setAdminRuleForm({ title: '', category: '', rule_type: 'blacklist', notes: '' });
      toast('Правило контента добавлено');
      loadAdminData();
    } catch {
      toast('Не удалось добавить правило', 'error');
    }
  }, [adminRuleForm, authFetch, isAdmin, loadAdminData, logout, toast, token]);

  const deleteAdminRule = useCallback(async (id) => {
    if (!token || !isAdmin) return;
    try {
      const r = await authFetch(`/api/admin/content-rules/${id}`, { method: 'DELETE' });
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('delete rule');
      toast('Правило удалено');
      loadAdminData();
    } catch {
      toast('Не удалось удалить правило', 'error');
    }
  }, [authFetch, isAdmin, loadAdminData, logout, toast, token]);

  const createPinned = useCallback(async () => {
    if (!token || !isAdmin) return;
    if (!adminPinnedForm.title || !adminPinnedForm.description) {
      return toast('Укажи title и description', 'error');
    }
    try {
      const r = await authFetch('/api/admin/pinned', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(adminPinnedForm)
      });
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('pinned');
      setAdminPinnedForm({
        title: '',
        year_genre: '',
        description: '',
        category: '',
        why_this: '',
        video_id: '',
        is_active: true
      });
      toast('Закрепленная рекомендация добавлена');
      loadAdminData();
    } catch {
      toast('Не удалось добавить закрепленную рекомендацию', 'error');
    }
  }, [adminPinnedForm, authFetch, isAdmin, loadAdminData, logout, toast, token]);

  const deletePinned = useCallback(async (id) => {
    if (!token || !isAdmin) return;
    try {
      const r = await authFetch(`/api/admin/pinned/${id}`, { method: 'DELETE' });
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('delete pinned');
      toast('Закрепленная рекомендация удалена');
      loadAdminData();
    } catch {
      toast('Не удалось удалить закрепленную рекомендацию', 'error');
    }
  }, [authFetch, isAdmin, loadAdminData, logout, toast, token]);

  const togglePinned = useCallback(async (item) => {
    if (!token || !isAdmin) return;
    try {
      const r = await authFetch(`/api/admin/pinned/${item.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: item.title,
          year_genre: item.year_genre || '',
          description: item.description,
          category: item.category || '',
          why_this: item.why_this || '',
          video_id: item.video_id || '',
          is_active: !item.is_active
        })
      });
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('toggle pinned');
      loadAdminData();
    } catch {
      toast('Не удалось изменить статус закрепления', 'error');
    }
  }, [authFetch, isAdmin, loadAdminData, logout, toast, token]);

  const downloadAdminExport = useCallback(async (scope, exportFormat) => {
    if (!token || !isAdmin) return;
    try {
      const r = await authFetch(`/api/admin/export?scope=${encodeURIComponent(scope)}&export_format=${encodeURIComponent(exportFormat)}`);
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('export');
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `admin_${scope}.${exportFormat}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast('Не удалось выгрузить отчет', 'error');
    }
  }, [authFetch, isAdmin, logout, toast, token]);

  useEffect(() => {
    if (!token) return;
    loadSessions();
    loadPrefs();
    loadInsights();
    loadOnboardingStatus();
  }, [token, loadSessions, loadPrefs, loadInsights, loadOnboardingStatus]);

  useEffect(() => {
    if (drawer && token) {
      loadSessions();
      loadPrefs();
    }
  }, [drawer, token, loadSessions, loadPrefs]);

  useEffect(() => {
    if (adminOpen && token && isAdmin) {
      loadAdminData();
    }
  }, [adminOpen, token, isAdmin, loadAdminData]);

  const savePrefs = useCallback(async () => {
    if (!token) return toast('Сначала войдите в аккаунт', 'error');
    setSavingPrefs(true);
    try {
      const r = await authFetch('/api/preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          favorite_categories: splitCsv(prefs.favorite_categories),
          disliked_categories: splitCsv(prefs.disliked_categories),
          favorite_platforms: splitCsv(prefs.favorite_platforms),
          preferred_language: prefs.preferred_language,
          age_rating: prefs.age_rating,
          discovery_mode: prefs.discovery_mode
        })
      });
      if (r.status === 401) return logout();
      const d = await r.json();
      setPrefs((p) => ({
        ...p,
        discovery_mode: d.discovery_mode || p.discovery_mode
      }));
      setCtx((p) => ({
        ...p,
        assistant_mode: d.discovery_mode || p.assistant_mode
      }));
      toast('Профиль ассистента сохранен');
    } catch {
      toast('Ошибка сохранения', 'error');
    } finally {
      setSavingPrefs(false);
    }
  }, [authFetch, logout, prefs, toast, token]);

  const submitOnboarding = useCallback(async () => {
    if (!token) return;
    setSavingOnboarding(true);
    try {
      const r = await authFetch('/api/onboarding/complete', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          favorite_categories: splitCsv(onboarding.favorite_categories),
          disliked_categories: splitCsv(onboarding.disliked_categories),
          favorite_platforms: splitCsv(onboarding.favorite_platforms),
          preferred_language: onboarding.preferred_language || 'ru',
          age_rating: prefs.age_rating || 'any',
          discovery_mode: onboarding.discovery_mode || 'balanced'
        })
      });
      if (r.status === 401) return logout();
      const data = await r.json();
      const next = data.preferences || {};
      setPrefs((p) => ({
        ...p,
        favorite_categories: (next.favorite_categories || splitCsv(onboarding.favorite_categories)).join(', '),
        disliked_categories: (next.disliked_categories || splitCsv(onboarding.disliked_categories)).join(', '),
        favorite_platforms: (next.favorite_platforms || splitCsv(onboarding.favorite_platforms)).join(', '),
        preferred_language: next.preferred_language || onboarding.preferred_language,
        discovery_mode: next.discovery_mode || onboarding.discovery_mode
      }));
      setCtx((p) => ({ ...p, assistant_mode: next.discovery_mode || onboarding.discovery_mode || p.assistant_mode }));
      setOnboardingOpen(false);
      toast('Онбординг сохранен. Ассистент стал точнее');
    } catch {
      toast('Не удалось сохранить онбординг', 'error');
    } finally {
      setSavingOnboarding(false);
    }
  }, [authFetch, logout, onboarding, prefs.age_rating, token, toast]);

  const handleAuth = useCallback(async () => {
    if (!loginUser || !loginPass) return toast('Заполните все поля', 'error');
    const endpoint = isRegister ? '/register' : '/token';
    let body;
    let headers;
    if (isRegister) {
      body = JSON.stringify({ username: loginUser, password: loginPass });
      headers = { 'Content-Type': 'application/json' };
    } else {
      const f = new URLSearchParams();
      f.append('username', loginUser);
      f.append('password', loginPass);
      body = f;
      headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
    }
    try {
      const r = await fetch(endpoint, { method: 'POST', headers, body });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Ошибка');
      setToken(d.access_token || '');
      setUser(d.username || '');
      setIsAdmin(Boolean(d.is_admin));
      localStorage.setItem('access_token', d.access_token || '');
      localStorage.setItem('username', d.username || '');
      localStorage.setItem('is_admin', String(Boolean(d.is_admin)));
      setLoginPass('');
      setSessionId(genSession());
      setMessages([]);
      setStarted(false);
      setOnboardingOpen(!Boolean(d.onboarding_completed));
      toast(isRegister ? 'Аккаунт создан' : 'Вход выполнен');
    } catch (e) {
      toast(e.message || 'Ошибка авторизации', 'error');
    }
  }, [isRegister, loginPass, loginUser, toast]);

  const send = useCallback(async (direct) => {
    const text = (direct ?? input).trim();
    if (!text) return;
    if (!token) return toast('Сначала войди в аккаунт', 'error');

    if (!started) setStarted(true);
    setInput('');

    const loaderId = genId();
    setMessages((p) => [
      ...p,
      { id: genId(), role: 'user', kind: 'text', text },
      { id: loaderId, role: 'ai', kind: 'loading' }
    ]);

    try {
      const r = await fetch('/recommend', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          query: text,
          session_id: sessionId,
          temporary: tempMode,
          mood: ctx.mood || null,
          company: ctx.company || null,
          time_minutes: ctx.time_minutes ? Number(ctx.time_minutes) : null,
          assistant_mode: ctx.assistant_mode || 'balanced'
        })
      });
      if (r.status === 401) {
        toast('Сессия истекла', 'error');
        return logout();
      }
      const d = await r.json();
      setMessages((p) => p.filter((m) => m.id !== loaderId));

      if (d.is_json && Array.isArray(d.recommendations)) {
        setMessages((p) => [
          ...p,
          {
            id: genId(),
            role: 'ai',
            kind: 'recommendations',
            requestText: text,
            source: d.source || 'llm',
            recommendations: d.recommendations
          }
        ]);
      } else {
        setMessages((p) => [...p, { id: genId(), role: 'ai', kind: 'markdown', text: String(d.recommendations || '') }]);
      }
      loadSessions();
      loadInsights();
    } catch {
      setMessages((p) => p.map((m) => (m.id === loaderId ? { ...m, kind: 'markdown', text: 'Ошибка связи :(' } : m)));
      toast('Не удалось получить ответ', 'error');
    }
  }, [ctx, input, loadInsights, loadSessions, logout, sessionId, started, tempMode, toast, token]);

  const sendFeedback = useCallback(async (recommendation, feedbackType, requestText, feedbackKey) => {
    if (!token) return;
    setFeedbackState((p) => ({ ...p, [feedbackKey]: feedbackType }));
    try {
      const r = await authFetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          query_text: requestText || '',
          title: recommendation?.title || '',
          category: recommendation?.category || '',
          feedback_type: feedbackType
        })
      });
      if (r.status === 401) return logout();
      if (!r.ok) throw new Error('Feedback failed');
      const map = {
        like: 'Сохранил: понравилось',
        dislike: 'Учту: не предлагать похожее',
        watched: 'Отмечено как просмотренное'
      };
      toast(map[feedbackType] || 'Фидбек сохранен');
      loadInsights();
    } catch {
      toast('Не удалось сохранить фидбек', 'error');
      setFeedbackState((p) => ({ ...p, [feedbackKey]: '' }));
    }
  }, [authFetch, loadInsights, logout, sessionId, toast, token]);

  const loadChat = useCallback(async (id) => {
    if (!token) return;
    setSessionId(id);
    setDrawer(false);
    setStarted(true);
    setMessages([{ id: genId(), role: 'ai', kind: 'markdown', text: 'Загрузка...' }]);
    try {
      const r = await authFetch(`/api/chat/${id}`);
      if (r.status === 401) return logout();
      const rows = await r.json();
      const out = [];
      rows.forEach((row) => {
        out.push({ id: genId(), role: 'user', kind: 'text', text: row.user_query || '' });
        if (row.ai_response_json) {
          try {
            const parsed = JSON.parse(row.ai_response_json);
            if (Array.isArray(parsed)) {
              out.push({
                id: genId(),
                role: 'ai',
                kind: 'recommendations',
                requestText: row.user_query || '',
                source: 'history',
                recommendations: parsed
              });
              return;
            }
          } catch {}
        }
        out.push({ id: genId(), role: 'ai', kind: 'markdown', text: row.ai_response || '' });
      });
      setActiveVideo({});
      setMessages(out);
    } catch {
      toast('Не удалось загрузить историю', 'error');
      setMessages([]);
    }
  }, [authFetch, logout, toast, token]);

  const connectText = isOnline
    ? 'Онлайн и готов к подбору'
    : 'Оффлайн режим: доступна установка PWA и история в браузере';

  return (
    <>
      <div className="background-container">
        <div className="blob blob-1" />
        <div className="blob blob-2" />
        <div className="blob blob-3" />
        <div className="anime-bg-layer" />
        <div className="grid-overlay" />
      </div>

      <div className="auth-overlay">
        <div className="auth-card">
          <div className="auth-title">
            <i className="ri-flashlight-fill" style={{ color: 'var(--primary)' }} />
            {' '}
            MEDIA
            <span>.AI</span>
          </div>
          <input
            className="auth-input"
            placeholder="Логин"
            value={loginUser}
            onChange={(e) => setLoginUser(e.target.value)}
          />
          <input
            className="auth-input"
            type="password"
            placeholder="Пароль"
            value={loginPass}
            onChange={(e) => setLoginPass(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAuth()}
          />
          <button className="auth-btn" onClick={handleAuth}>
            {isRegister ? 'Зарегистрироваться' : 'Войти'}
          </button>
          <div className="auth-switch" onClick={() => setIsRegister((v) => !v)}>
            {isRegister ? 'Уже есть аккаунт? Войти' : 'Нет аккаунта? Зарегистрироваться'}
          </div>
        </div>
      </div>

      {onboardingOpen && (
        <div className="onboarding-overlay">
          <div className="onboarding-card">
            <h3>Быстрый старт ассистента</h3>
            <p>Ответь на 5 вопросов, и рекомендации станут заметно точнее.</p>
            <div className="onboarding-form">
              <label>1. Любимые категории</label>
              <input
                className="prefs-input"
                value={onboarding.favorite_categories}
                onChange={(e) => setOnboarding((p) => ({ ...p, favorite_categories: e.target.value }))}
                placeholder="аниме, sci-fi, триллер"
              />
              <label>2. Что не предлагать</label>
              <input
                className="prefs-input"
                value={onboarding.disliked_categories}
                onChange={(e) => setOnboarding((p) => ({ ...p, disliked_categories: e.target.value }))}
                placeholder="хоррор, реалити"
              />
              <label>3. Где обычно смотришь/играешь</label>
              <input
                className="prefs-input"
                value={onboarding.favorite_platforms}
                onChange={(e) => setOnboarding((p) => ({ ...p, favorite_platforms: e.target.value }))}
                placeholder="Netflix, Steam, YouTube"
              />
              <label>4. Язык рекомендаций</label>
              <select
                className="prefs-select"
                value={onboarding.preferred_language}
                onChange={(e) => setOnboarding((p) => ({ ...p, preferred_language: e.target.value }))}
              >
                {LANGS.map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
              <label>5. Режим ассистента</label>
              <select
                className="prefs-select"
                value={onboarding.discovery_mode}
                onChange={(e) => setOnboarding((p) => ({ ...p, discovery_mode: e.target.value }))}
              >
                {MODES.map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
            <div className="onboarding-actions">
              <button className="hero-cta" onClick={() => setOnboardingOpen(false)}>Позже</button>
              <button className="hero-cta primary" onClick={submitOnboarding} disabled={savingOnboarding}>
                {savingOnboarding ? 'Сохраняю...' : 'Завершить'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="app-content">
        <nav className="navbar">
          <div className="nav-left">
            <button className="menu-btn" onClick={() => setDrawer((v) => !v)}>
              <i className="ri-menu-fill" />
            </button>
            <div className="logo">
              <i className="ri-flashlight-fill" />
              <span>MEDIA.AI</span>
              <span className="admin-badge" style={{ display: 'none' }}>ADMIN</span>
            </div>
          </div>
          <div className="nav-right">
            <button
              className="download-btn"
              onClick={() => window.open(DOWNLOAD_URL, '_blank', 'noopener,noreferrer')}
            >
              <i className="ri-download-line" />
            </button>
            <button
              className={`install-btn-nav ${deferred ? '' : 'hidden'}`}
              onClick={async () => {
                if (!deferred) return toast('Установка пока недоступна', 'error');
                deferred.prompt();
                await deferred.userChoice;
                setDeferred(null);
                toast('MediaAI добавлен как приложение');
              }}
            >
              <i className="ri-smartphone-line" />
            </button>
            <button ref={themeBtnRef} className="theme-btn" onClick={() => setThemeOpen((v) => !v)}>
              <i className="ri-palette-line" />
            </button>
            <button className="logout-btn" onClick={logout}>
              <i className="ri-logout-box-r-line" />
            </button>
          </div>
        </nav>

        <div ref={dropdownRef} className={`theme-dropdown ${themeOpen ? 'show' : ''}`}>
          {THEMES.map(([v, l, c]) => (
            <div key={v || 'default'} className="theme-opt" onClick={() => { setTheme(v); setThemeOpen(false); }}>
              <div className="color-dot" style={{ background: c }} />
              {l}
            </div>
          ))}
        </div>

        <div className="container">
          <div className="hero-content" id="hero">
            <div className={`status-pill ${isOnline ? '' : 'offline'}`}>
              <span className="status-dot" />
              <span>{connectText}</span>
            </div>
            <h1>
              Развлечения
              <br />
              будущего
            </h1>
            <p className="subtitle">Персональный ассистент подберет контент под твои вкусы и контекст.</p>
            <div className="hero-stats">
              <div className="hero-stat"><strong>{insights.total_queries}</strong><span>Запросов</span></div>
              <div className="hero-stat"><strong>{insights.total_sessions}</strong><span>Сессий</span></div>
              <div className="hero-stat"><strong>{insights.favorite_category}</strong><span>Любимая категория</span></div>
            </div>
            <div className="insight-tags">
              {insights.top_categories.map((t) => (
                <span key={t} className="insight-tag">{t}</span>
              ))}
            </div>
            <div className="suggestions-grid">
              {QUICK.map(([icon, text]) => (
                <div key={text} className="chip" onClick={() => send(text)}>
                  <i className={icon} />
                  {' '}
                  {text}
                </div>
              ))}
            </div>
          </div>

          <div className="chat-stream" ref={streamRef}>
            {messages.map((m) => (
              <div key={m.id} className={`msg-row ${m.role}`}>
                {m.role === 'ai' && (
                  <div className="avatar">
                    <i className="ri-robot-2-fill" />
                  </div>
                )}
                <div className="msg-bubble">
                  {m.kind === 'loading' && (
                    <div className="typing">
                      <div className="dot" />
                      <div className="dot" />
                      <div className="dot" />
                    </div>
                  )}

                  {m.kind === 'text' && m.text}

                  {m.kind === 'markdown' && (
                    <div dangerouslySetInnerHTML={{ __html: marked.parse(m.text || '') }} />
                  )}

                  {m.kind === 'recommendations' && (
                    <div className="rec-container">
                      {m.recommendations.map((it, idx) => {
                        const v = it.video_id;
                        const key = `${m.id}-${idx}`;
                        const loaded = !!activeVideo[key];
                        const fb = feedbackState[key] || '';
                        return (
                          <div key={key} className="rec-card">
                            {v && (
                              <div className="video-wrapper" onClick={() => setActiveVideo((p) => ({ ...p, [key]: true }))}>
                                {loaded ? (
                                  <iframe
                                    src={`https://www.youtube.com/embed/${v}?autoplay=1`}
                                    allowFullScreen
                                    allow="autoplay"
                                    title={it.title || key}
                                  />
                                ) : (
                                  <>
                                    <img
                                      className="thumb-img"
                                      src={`https://img.youtube.com/vi/${v}/hqdefault.jpg`}
                                      alt={it.title || 'Trailer'}
                                    />
                                    <div className="play-overlay">
                                      <div className="play-btn"><i className="ri-play-fill" /></div>
                                    </div>
                                  </>
                                )}
                              </div>
                            )}
                            <div className="rec-header">
                              <div className="rec-title">{it.title}</div>
                              <div className="rec-meta">{it.year_genre || it.category || ''}</div>
                            </div>
                            {it.why_this && (
                              <div className="why-this">
                                <i className="ri-sparkling-2-fill" />
                                <span>{it.why_this}</span>
                              </div>
                            )}
                            <div
                              className="rec-desc"
                              dangerouslySetInnerHTML={{
                                __html: marked.parse(autoHighlightDescription(it.description || '', it.title || ''))
                              }}
                            />
                            <div className="rec-actions">
                              <button onClick={() => setFavorites((p) => (p.includes(it.title) ? p : [it.title, ...p].slice(0, 25)))}>
                                <i className="ri-heart-3-line" />
                                В избранное
                              </button>
                              <button
                                className={fb === 'like' ? 'feedback-active' : ''}
                                onClick={() => sendFeedback(it, 'like', m.requestText, key)}
                              >
                                <i className="ri-thumb-up-line" />
                                Нравится
                              </button>
                              <button
                                className={fb === 'dislike' ? 'feedback-active' : ''}
                                onClick={() => sendFeedback(it, 'dislike', m.requestText, key)}
                              >
                                <i className="ri-thumb-down-line" />
                                Не подходит
                              </button>
                              <button
                                className={fb === 'watched' ? 'feedback-active' : ''}
                                onClick={() => sendFeedback(it, 'watched', m.requestText, key)}
                              >
                                <i className="ri-eye-line" />
                                Уже смотрел
                              </button>
                              <button
                                onClick={() => navigator.clipboard
                                  .writeText(it.title || '')
                                  .then(() => toast('Скопировано'))
                                  .catch(() => toast('Не удалось скопировать', 'error'))}
                              >
                                <i className="ri-file-copy-line" />
                                Скопировать
                              </button>
                              {v && (
                                <button onClick={() => window.open(`https://www.youtube.com/watch?v=${v}`, '_blank', 'noopener,noreferrer')}>
                                  <i className="ri-youtube-line" />
                                  Открыть YouTube
                                </button>
                              )}
                              {isGameRecommendation(it, m.requestText) && (
                                <button onClick={() => window.open(steamSearchUrl(it.title), '_blank', 'noopener,noreferrer')}>
                                  <i className="ri-gamepad-line" />
                                  Открыть Steam
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="assistant-context-bar">
          <select
            className="assistant-select"
            value={ctx.assistant_mode}
            onChange={(e) => setCtx((p) => ({ ...p, assistant_mode: e.target.value }))}
          >
            {MODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select
            className="assistant-select"
            value={ctx.mood}
            onChange={(e) => setCtx((p) => ({ ...p, mood: e.target.value }))}
          >
            <option value="">Любое настроение</option>
            <option value="relax">Расслабиться</option>
            <option value="focus">Сфокусироваться</option>
            <option value="fun">Поднять настроение</option>
          </select>
          <select
            className="assistant-select"
            value={ctx.company}
            onChange={(e) => setCtx((p) => ({ ...p, company: e.target.value }))}
          >
            <option value="">Любая компания</option>
            <option value="solo">Один</option>
            <option value="friends">С друзьями</option>
            <option value="family">С семьей</option>
          </select>
          <input
            className="assistant-time-input"
            type="number"
            min="15"
            max="300"
            step="15"
            placeholder="Минут"
            value={ctx.time_minutes}
            onChange={(e) => setCtx((p) => ({ ...p, time_minutes: e.target.value }))}
          />
        </div>

        <div className="input-dock">
          <button
            className="dock-btn"
            onClick={() => {
              setSessionId(genSession());
              setMessages([]);
              setStarted(false);
              setDrawer(false);
              setFeedbackState({});
            }}
          >
            <i className="ri-refresh-line" />
          </button>
          <button
            className={`dock-btn temp-toggle ${tempMode ? 'active' : ''}`}
            onClick={() => {
              setTempMode((v) => !v);
              toast(!tempMode ? 'Временный режим включен' : 'Временный режим выключен');
            }}
          >
            <i className="ri-spy-line" />
          </button>
          <input
            placeholder="Что будем искать?"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
          />
          <button className="dock-btn btn-send" onClick={() => send()}>
            <i className="ri-arrow-up-line" />
          </button>
        </div>
      </div>

      <div className={`drawer ${drawer ? 'open' : ''}`}>
        <div className="drawer-head">
          <h2 style={{ fontFamily: 'Montserrat', margin: 0 }}>MEDIA.AI</h2>
          <button className="drawer-close-btn" onClick={() => setDrawer(false)} aria-label="Закрыть меню">
            <i className="ri-close-line" />
          </button>
        </div>
        <div className="user-profile">Пользователь: {user || 'Гость'}</div>
        <button
          className="new-chat-btn-sidebar"
          onClick={() => {
            setSessionId(genSession());
            setMessages([]);
            setStarted(false);
            setDrawer(false);
            setFeedbackState({});
          }}
        >
          <i className="ri-add-line" />
          {' '}
          Новый чат
        </button>

        <div className="toolbar-title">История сессий</div>
        {isAdmin && (
          <button className="new-chat-btn-sidebar admin-open-btn" onClick={() => setAdminOpen(true)}>
            <i className="ri-shield-star-line" />
            {' '}
            Admin Panel
          </button>
        )}
        <div className="history-list">
          {sessionsState ? (
            <div style={{ padding: 10, color: '#666' }}>{sessionsState}</div>
          ) : (
            sessions.map((s) => (
              <div key={s.session_id} className="history-item session-item" onClick={() => loadChat(s.session_id)}>
                <div className="session-head">
                  <span className="session-title">{s.title}</span>
                  <span className="session-count">
                    {s.message_count || 0}
                    {' '}
                    запрос.
                  </span>
                </div>
                {s.preview && <div className="session-preview">{s.preview}</div>}
                {s.last_timestamp && <div className="session-date">{formatSessionTime(s.last_timestamp)}</div>}
              </div>
            ))
          )}
        </div>

        <div className="section-divider" />
        <div className="toolbar-title">Избранное</div>
        <div className="favorites-wrap">
          {!favorites.length ? (
            <div className="favorites-empty">Пока пусто. Сохрани рекомендации, и они появятся здесь.</div>
          ) : (
            favorites.map((f) => (
              <div key={f} className="favorite-item">
                <span title={f}>{f}</span>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="mini-btn" onClick={() => send(f)} title="Найти снова">
                    <i className="ri-search-line" />
                  </button>
                  <button className="mini-btn" onClick={() => setFavorites((p) => p.filter((x) => x !== f))} title="Удалить">
                    <i className="ri-delete-bin-6-line" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="section-divider" />
        <div className="toolbar-title">Профиль ассистента</div>
        <div className="prefs-form">
          <label>Любимые категории</label>
          <input
            className="prefs-input"
            value={prefs.favorite_categories}
            onChange={(e) => setPrefs((p) => ({ ...p, favorite_categories: e.target.value }))}
            placeholder="фильмы, аниме, инди-игры"
          />
          <label>Что не предлагать</label>
          <input
            className="prefs-input"
            value={prefs.disliked_categories}
            onChange={(e) => setPrefs((p) => ({ ...p, disliked_categories: e.target.value }))}
            placeholder="хоррор, реалити"
          />
          <label>Платформы</label>
          <input
            className="prefs-input"
            value={prefs.favorite_platforms}
            onChange={(e) => setPrefs((p) => ({ ...p, favorite_platforms: e.target.value }))}
            placeholder="Netflix, Steam, YouTube"
          />
          <label>Язык</label>
          <select
            className="prefs-select"
            value={prefs.preferred_language}
            onChange={(e) => setPrefs((p) => ({ ...p, preferred_language: e.target.value }))}
          >
            {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <label>Возрастной фильтр</label>
          <select
            className="prefs-select"
            value={prefs.age_rating}
            onChange={(e) => setPrefs((p) => ({ ...p, age_rating: e.target.value }))}
          >
            {RATINGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <label>Режим по умолчанию</label>
          <select
            className="prefs-select"
            value={prefs.discovery_mode}
            onChange={(e) => setPrefs((p) => ({ ...p, discovery_mode: e.target.value }))}
          >
            {MODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button className="prefs-save-btn" onClick={savePrefs} disabled={savingPrefs}>
            {savingPrefs ? 'Сохраняю...' : 'Сохранить профиль'}
          </button>
        </div>
      </div>

      {adminOpen && isAdmin && (
        <div className="admin-overlay">
          <div className="admin-card">
            <div className="admin-head">
              <h3>Админ-панель</h3>
              <button className="drawer-close-btn" onClick={() => setAdminOpen(false)}>
                <i className="ri-close-line" />
              </button>
            </div>
            <div className="admin-tabs">
              {['stats', 'users', 'content', 'settings', 'export'].map((tab) => (
                <button
                  key={tab}
                  className={`admin-tab-btn ${adminTab === tab ? 'active' : ''}`}
                  onClick={() => setAdminTab(tab)}
                >
                  {tab}
                </button>
              ))}
              <button className="admin-tab-btn" onClick={loadAdminData} disabled={adminBusy}>
                {adminBusy ? 'loading...' : 'refresh'}
              </button>
            </div>
            <div className="admin-body">
              {adminTab === 'stats' && (
                <div className="admin-grid">
                  <div className="admin-stat"><strong>{adminStats?.users_total ?? 0}</strong><span>Users</span></div>
                  <div className="admin-stat"><strong>{adminStats?.queries_total ?? 0}</strong><span>Queries</span></div>
                  <div className="admin-stat"><strong>{adminStats?.feedback_total ?? 0}</strong><span>Feedback</span></div>
                  <div className="admin-stat"><strong>{adminStats?.api_429_count ?? 0}</strong><span>429</span></div>
                  <div className="admin-list">
                    <h4>Top Queries</h4>
                    {(adminStats?.top_queries || []).map((q) => (
                      <div key={q.query} className="admin-list-row">{q.query} <b>{q.count}</b></div>
                    ))}
                  </div>
                  <div className="admin-list">
                    <h4>Model Usage</h4>
                    {(adminStats?.model_usage || []).map((m) => (
                      <div key={m.model} className="admin-list-row">{m.model} <b>{m.count}</b></div>
                    ))}
                  </div>
                </div>
              )}
              {adminTab === 'users' && (
                <div className="admin-table-wrap">
                  <table className="admin-table">
                    <thead>
                      <tr><th>id</th><th>user</th><th>role</th><th>blocked</th><th>limit</th><th>today</th><th>actions</th></tr>
                    </thead>
                    <tbody>
                      {adminUsers.map((u) => (
                        <tr key={u.id}>
                          <td>{u.id}</td>
                          <td>{u.username}</td>
                          <td>{u.is_admin ? 'admin' : 'user'}</td>
                          <td>{u.is_blocked ? 'yes' : 'no'}</td>
                          <td>{u.daily_limit || u.effective_daily_limit}</td>
                          <td>{u.queries_today}</td>
                          <td className="admin-actions">
                            <button onClick={() => updateAdminUser(u.id, { is_blocked: !u.is_blocked })}>
                              {u.is_blocked ? 'unblock' : 'block'}
                            </button>
                            <button onClick={() => updateAdminUser(u.id, { is_admin: !u.is_admin })}>
                              {u.is_admin ? 'remove admin' : 'make admin'}
                            </button>
                            <button onClick={() => {
                              const v = window.prompt('Daily limit', String(u.daily_limit || u.effective_daily_limit || 40));
                              if (!v) return;
                              const n = Number(v);
                              if (!Number.isFinite(n) || n < 1) return toast('Некорректный лимит', 'error');
                              updateAdminUser(u.id, { daily_limit: Math.floor(n) });
                            }}>
                              set limit
                            </button>
                            <button onClick={() => resetUserHistory(u.id)}>reset history</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {adminTab === 'content' && (
                <div className="admin-content-wrap">
                  <div className="admin-form-card">
                    <h4>Rule (blacklist / whitelist)</h4>
                    <input className="prefs-input" placeholder="title" value={adminRuleForm.title} onChange={(e) => setAdminRuleForm((p) => ({ ...p, title: e.target.value }))} />
                    <input className="prefs-input" placeholder="category" value={adminRuleForm.category} onChange={(e) => setAdminRuleForm((p) => ({ ...p, category: e.target.value }))} />
                    <select className="prefs-select" value={adminRuleForm.rule_type} onChange={(e) => setAdminRuleForm((p) => ({ ...p, rule_type: e.target.value }))}>
                      <option value="blacklist">blacklist</option>
                      <option value="whitelist">whitelist</option>
                    </select>
                    <input className="prefs-input" placeholder="notes" value={adminRuleForm.notes} onChange={(e) => setAdminRuleForm((p) => ({ ...p, notes: e.target.value }))} />
                    <button className="prefs-save-btn" onClick={createAdminRule}>add rule</button>
                    <div className="admin-list scroll-y">
                      {adminRules.map((r) => (
                        <div key={r.id} className="admin-list-row">
                          <span>{r.rule_type}: {r.title || '-'} / {r.category || '-'}</span>
                          <button onClick={() => deleteAdminRule(r.id)}>delete</button>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="admin-form-card">
                    <h4>Pinned recommendations</h4>
                    <input className="prefs-input" placeholder="title" value={adminPinnedForm.title} onChange={(e) => setAdminPinnedForm((p) => ({ ...p, title: e.target.value }))} />
                    <input className="prefs-input" placeholder="year_genre" value={adminPinnedForm.year_genre} onChange={(e) => setAdminPinnedForm((p) => ({ ...p, year_genre: e.target.value }))} />
                    <input className="prefs-input" placeholder="category" value={adminPinnedForm.category} onChange={(e) => setAdminPinnedForm((p) => ({ ...p, category: e.target.value }))} />
                    <textarea className="prefs-input admin-textarea" placeholder="description" value={adminPinnedForm.description} onChange={(e) => setAdminPinnedForm((p) => ({ ...p, description: e.target.value }))} />
                    <input className="prefs-input" placeholder="why_this" value={adminPinnedForm.why_this} onChange={(e) => setAdminPinnedForm((p) => ({ ...p, why_this: e.target.value }))} />
                    <input className="prefs-input" placeholder="video_id" value={adminPinnedForm.video_id} onChange={(e) => setAdminPinnedForm((p) => ({ ...p, video_id: e.target.value }))} />
                    <button className="prefs-save-btn" onClick={createPinned}>add pinned</button>
                    <div className="admin-list scroll-y">
                      {adminPinned.map((r) => (
                        <div key={r.id} className="admin-list-row">
                          <span>{r.is_active ? 'ON' : 'OFF'}: {r.title}</span>
                          <div className="admin-actions">
                            <button onClick={() => togglePinned(r)}>{r.is_active ? 'disable' : 'enable'}</button>
                            <button onClick={() => deletePinned(r.id)}>delete</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
              {adminTab === 'settings' && (
                <div className="admin-form-card">
                  <h4>Runtime settings</h4>
                  <label className="admin-check">
                    <input
                      type="checkbox"
                      checked={Boolean(adminSettings.force_lite_mode)}
                      onChange={(e) => setAdminSettings((p) => ({ ...p, force_lite_mode: e.target.checked }))}
                    />
                    Force lite mode
                  </label>
                  <label>Default daily limit</label>
                  <input
                    className="prefs-input"
                    type="number"
                    min="1"
                    value={adminSettings.default_daily_limit}
                    onChange={(e) => setAdminSettings((p) => ({ ...p, default_daily_limit: Number(e.target.value || 1) }))}
                  />
                  <button className="prefs-save-btn" onClick={saveAdminSettings}>save settings</button>
                </div>
              )}
              {adminTab === 'export' && (
                <div className="admin-form-card">
                  <h4>Export reports</h4>
                  <div className="admin-actions">
                    <button onClick={() => downloadAdminExport('users', 'json')}>users.json</button>
                    <button onClick={() => downloadAdminExport('users', 'csv')}>users.csv</button>
                    <button onClick={() => downloadAdminExport('history', 'json')}>history.json</button>
                    <button onClick={() => downloadAdminExport('history', 'csv')}>history.csv</button>
                    <button onClick={() => downloadAdminExport('feedback', 'json')}>feedback.json</button>
                    <button onClick={() => downloadAdminExport('usage', 'json')}>usage.json</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="drawer-overlay" onClick={() => setDrawer(false)} />
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>{t.text}</div>
        ))}
      </div>
    </>
  );
}
