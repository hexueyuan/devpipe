// ============================================================
// Devpipe Dashboard — 统一前端
// 支持 Flask (live) 和 GitHub Pages (static) 双模式
// ============================================================

// ========================
// 1. 环境检测与配置
// ========================

function detectMode() {
    if (location.hostname.includes('github.io') || location.protocol === 'file:') {
        return {
            mode: 'static',
            github: { owner: 'hexueyuan', repo: 'devpipe', dataPath: 'docs/devpipe' }
        };
    }
    return { mode: 'live', apiBase: location.origin };
}

const CONFIG = detectMode();

// ========================
// 2. 常量定义（移植自 worktree_service.py）
// ========================

const STAGES = ['init', 'discuss', 'design', 'coding', 'review-and-fix', 'summarize', 'done'];

const STAGE_LABELS = {
    'init': '初始化',
    'discuss': '需求讨论',
    'design': '方案设计',
    'coding': '代码开发',
    'review-and-fix': '评审修复',
    'summarize': '总结',
    'done': '已完成'
};

const STAGE_META = {
    'init':           { is_core: false, roles: '\uD83E\uDD16',    role_desc: 'Agent 自动' },
    'discuss':        { is_core: true,  roles: '\uD83D\uDC64\uD83E\uDD16', role_desc: '人 + Agent' },
    'design':         { is_core: true,  roles: '\uD83D\uDC64\uD83E\uDD16', role_desc: '人 + Agent' },
    'coding':         { is_core: true,  roles: '\uD83E\uDD16',    role_desc: 'Agent' },
    'review-and-fix': { is_core: true,  roles: '\uD83D\uDC64\uD83E\uDD16', role_desc: '人 + Agent' },
    'summarize':      { is_core: false, roles: '\uD83D\uDC64\uD83E\uDD16', role_desc: '人 + Agent' },
    'done':           { is_core: false, roles: '',      role_desc: '' }
};

const STAGE_DOCUMENT_MAP = {
    'init': { filename: null, placeholder: '初始化阶段无关联文档' },
    'discuss': { filename: 'prd.md', placeholder: '尚未生成文档' },
    'design': { filename: 'coding-plan.md', placeholder: '尚未生成文档' },
    'coding': { filename: 'task-progress.md', placeholder: '尚未生成文档' },
    'review-and-fix': { filename: 'review-status.md', placeholder: '尚未生成文档' },
    'summarize': { filename: 'summary.md', placeholder: '尚未生成文档' }
};

const TIMELINE_GROUPS = [
    { name: '环境准备', stages: ['init'] },
    { name: '工作流程', stages: ['discuss', 'design', 'coding', 'review-and-fix'] },
    { name: '总结复盘', stages: ['summarize'] }
];

// ========================
// 3. 业务逻辑函数（移植自 Python）
// ========================

/**
 * 计算有效阶段（考虑 stage_completed 的推进逻辑）
 */
function getEffectiveStage(ctx) {
    if (!ctx || !ctx.stage) return 'init';
    var stage = ctx.stage;
    var completed = ctx.stage_completed || false;
    var devType = ctx.dev_type || '';

    if (completed && stage !== 'done') {
        var nextMap;
        if (devType === '新功能') {
            nextMap = {
                'init': 'discuss', 'discuss': 'design',
                'design': 'coding', 'coding': 'review-and-fix',
                'review-and-fix': 'summarize', 'summarize': 'done'
            };
        } else {
            nextMap = {
                'init': 'design',
                'design': 'coding', 'coding': 'review-and-fix',
                'review-and-fix': 'summarize', 'summarize': 'done'
            };
        }
        stage = nextMap[stage] || stage;
    }
    return stage;
}

/**
 * 解析子任务表格
 */
function parseSubtasks(md) {
    if (!md) return [];
    var subtasks = [];
    var pattern = /\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(已完成|当前|待执行)\s*\|/g;
    var match;
    while ((match = pattern.exec(md)) !== null) {
        subtasks.push({
            index: parseInt(match[1]),
            name: match[2].trim(),
            module: match[3].trim(),
            status: match[4].trim()
        });
    }
    return subtasks;
}

/**
 * 解析验收标准
 */
function parseAcceptanceCriteria(md) {
    if (!md) return [];
    var criteria = [];
    var lines = md.split('\n');
    var inSection = false;
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (line.indexOf('## 验收标准') !== -1) {
            inSection = true;
            continue;
        }
        if (inSection) {
            if (line.startsWith('## ')) break;
            var m = line.match(/^\s*(?:\d+\.\s*|-\s*)(.+)$/);
            if (m) criteria.push(m[1].trim());
        }
    }
    return criteria;
}

/**
 * 计算阶段持续时间（秒）
 */
function calcStageDuration(startedAt, endedAt) {
    if (!startedAt || !endedAt) return null;
    var start = new Date(startedAt);
    var end = new Date(endedAt);
    if (isNaN(start.getTime()) || isNaN(end.getTime())) return null;
    return Math.floor((end - start) / 1000);
}

/**
 * 格式化持续时间
 */
function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return '进行中';
    if (seconds < 0) return '-';
    if (seconds < 60) return seconds + '秒';
    if (seconds < 3600) {
        var m = Math.floor(seconds / 60);
        var s = seconds % 60;
        return s === 0 ? m + '分' : m + '分' + s + '秒';
    }
    var h = Math.floor(seconds / 3600);
    var mins = Math.floor((seconds % 3600) / 60);
    return mins === 0 ? h + '小时' : h + '小时' + mins + '分';
}

/**
 * 获取阶段时间统计列表
 */
function getStageTimes(ctx, currentStage, devType) {
    if (!ctx) return [];
    var ts = ctx.stage_timestamps || {};
    if (Object.keys(ts).length === 0) return [];

    var applicable;
    if (devType === '新功能') {
        applicable = ['init', 'discuss', 'design', 'coding', 'review-and-fix', 'summarize'];
    } else {
        applicable = ['init', 'design', 'coding', 'review-and-fix', 'summarize'];
    }

    var currentIndex = applicable.indexOf(currentStage);
    var result = [];

    for (var i = 0; i < applicable.length; i++) {
        var stage = applicable[i];
        var stageTs = ts[stage] || {};
        var started = stageTs.started_at || null;
        var ended = stageTs.ended_at || null;
        var duration = calcStageDuration(started, ended);

        var isCurrent = (stage === currentStage);
        var isCompleted;
        if (currentStage === 'done') {
            isCompleted = true;
            isCurrent = false;
        } else {
            isCompleted = (i < currentIndex) || (ended !== null);
        }

        var durationDisplay = '';
        if (started) {
            durationDisplay = formatDuration(duration);
        }

        var meta = STAGE_META[stage] || { is_core: false, roles: '', role_desc: '' };

        result.push({
            stage: stage,
            label: STAGE_LABELS[stage] || stage,
            started_at: started,
            ended_at: ended,
            duration_seconds: duration,
            duration_display: durationDisplay,
            is_current: isCurrent,
            is_completed: isCompleted,
            is_core: meta.is_core,
            roles: meta.roles,
            role_desc: meta.role_desc
        });
    }
    return result;
}

/**
 * 获取 Timeline 分组数据
 */
function getTimelineGroups(ctx, currentStage, devType) {
    if (!ctx) return [];
    var ts = ctx.stage_timestamps || {};
    if (Object.keys(ts).length === 0) return [];

    var result = [];
    for (var g = 0; g < TIMELINE_GROUPS.length; g++) {
        var groupDef = TIMELINE_GROUPS[g];
        var groupName = groupDef.name;
        var groupStages = groupDef.stages.slice();

        if (devType !== '新功能' && groupName === '工作流程') {
            groupStages = groupStages.filter(function(s) { return s !== 'discuss'; });
        }

        var totalSeconds = 0;
        var hasStarted = false;
        var allCompleted = true;
        var anyCurrent = false;

        for (var i = 0; i < groupStages.length; i++) {
            var stage = groupStages[i];
            var stageTs = ts[stage] || {};
            var started = stageTs.started_at || null;
            var ended = stageTs.ended_at || null;

            if (started) {
                hasStarted = true;
                if (ended) {
                    var d = calcStageDuration(started, ended);
                    if (d !== null) totalSeconds += d;
                } else {
                    allCompleted = false;
                }
            }

            if (stage === currentStage) {
                anyCurrent = true;
                allCompleted = false;
            }
            if (!ended) allCompleted = false;
        }

        var isCompleted, isCurrent;
        if (currentStage === 'done') {
            isCompleted = true;
            isCurrent = false;
        } else {
            isCompleted = hasStarted && allCompleted;
            isCurrent = anyCurrent || (hasStarted && !allCompleted);
        }

        var durationDisplay;
        if (!hasStarted) {
            durationDisplay = '-';
        } else if (isCompleted) {
            durationDisplay = formatDuration(totalSeconds);
        } else {
            durationDisplay = '进行中';
        }

        result.push({
            name: groupName,
            stages: groupStages,
            duration_seconds: isCompleted ? totalSeconds : null,
            duration_display: durationDisplay,
            is_completed: isCompleted,
            is_current: isCurrent
        });
    }
    return result;
}

/**
 * 格式化时间戳为 YYYY-MM-DD HH:MM:SS
 */
function formatDatetime(value) {
    if (!value || value === '-') return '-';
    try {
        var d = new Date(value);
        if (isNaN(d.getTime())) return value;
        var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
            ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
    } catch (e) {
        return value;
    }
}

// ========================
// 4. 缓存层
// ========================

var CACHE_TTL = 5 * 60 * 1000; // 5 分钟

function cacheGet(key) {
    try {
        var item = sessionStorage.getItem('dp_' + key);
        if (!item) return null;
        var parsed = JSON.parse(item);
        if (Date.now() - parsed.ts > CACHE_TTL) {
            sessionStorage.removeItem('dp_' + key);
            return null;
        }
        return parsed.data;
    } catch (e) {
        return null;
    }
}

function cacheSet(key, data) {
    try {
        sessionStorage.setItem('dp_' + key, JSON.stringify({ ts: Date.now(), data: data }));
    } catch (e) {
        // sessionStorage full, ignore
    }
}

// ========================
// 5. 数据获取层
// ========================

async function fetchIterations() {
    if (CONFIG.mode === 'live') return fetchIterationsFromFlask();
    return fetchIterationsFromGitHub();
}

async function fetchIterationDetail(name) {
    if (CONFIG.mode === 'live') return fetchDetailFromFlask(name);
    return fetchDetailFromGitHub(name);
}

// --- Flask 数据源 ---

async function fetchIterationsFromFlask() {
    var resp = await fetch(CONFIG.apiBase + '/api/worktrees');
    if (!resp.ok) throw new Error('API 请求失败: ' + resp.status);
    var data = await resp.json();
    return data.worktrees || [];
}

async function fetchDetailFromFlask(name) {
    var resp = await fetch(CONFIG.apiBase + '/api/worktree/' + encodeURIComponent(name));
    if (!resp.ok) throw new Error('API 请求失败: ' + resp.status);
    return await resp.json();
}

// --- GitHub 数据源 ---

async function githubApiFetch(path) {
    var cacheKey = 'gh_' + path;
    var cached = cacheGet(cacheKey);
    if (cached) return cached;

    var url = 'https://api.github.com/repos/' + CONFIG.github.owner + '/' + CONFIG.github.repo + '/contents/' + path;
    var resp = await fetch(url);
    if (resp.status === 403) {
        throw new Error('GitHub API 速率限制（60次/小时），请稍后再试');
    }
    if (resp.status === 404) return null;
    if (!resp.ok) throw new Error('GitHub API 错误: ' + resp.status);

    var data = await resp.json();
    cacheSet(cacheKey, data);
    return data;
}

async function githubFileContent(path) {
    var data = await githubApiFetch(path);
    if (!data || !data.content) return null;
    return atob(data.content.replace(/\n/g, ''));
}

async function fetchIterationsFromGitHub() {
    var entries = await githubApiFetch(CONFIG.github.dataPath);
    if (!entries || !Array.isArray(entries)) return [];

    var iterations = [];
    for (var i = 0; i < entries.length; i++) {
        var entry = entries[i];
        if (entry.type !== 'dir') continue;

        try {
            var ctxStr = await githubFileContent(CONFIG.github.dataPath + '/' + entry.name + '/context.json');
            if (!ctxStr) continue;
            var ctx = JSON.parse(ctxStr);

            var stage = getEffectiveStage(ctx);
            var devType = ctx.dev_type || '-';

            // 读取 task-progress.md 用于列表页进度条
            var taskProgressMd = null;
            if (stage === 'coding' || stage === 'review-and-fix') {
                taskProgressMd = await githubFileContent(CONFIG.github.dataPath + '/' + entry.name + '/task-progress.md');
            }

            var subtasks = parseSubtasks(taskProgressMd);
            var completed = subtasks.filter(function(s) { return s.status === '已完成'; }).length;

            iterations.push({
                name: entry.name,
                dev_type: devType,
                description: ctx.description || '-',
                summary: ctx.description || '-',
                stage: stage,
                stage_label: STAGE_LABELS[stage] || stage,
                stage_completed: ctx.stage_completed || false,
                created_at: formatDatetime(ctx.created_at),
                github_issue: ctx.github_issue || '',
                github_issue_title: ctx.github_issue_title || '',
                github_issue_url: ctx.github_issue_url || '',
                subtask_completed: completed,
                subtask_total: subtasks.length,
                is_archived: true,
                _context: ctx
            });
        } catch (e) {
            console.warn('跳过迭代目录:', entry.name, e);
        }
    }

    // 按创建时间倒序
    iterations.sort(function(a, b) {
        return (b.created_at || '').localeCompare(a.created_at || '');
    });

    return iterations;
}

async function fetchDetailFromGitHub(name) {
    var basePath = CONFIG.github.dataPath + '/' + name;
    var ctxStr = await githubFileContent(basePath + '/context.json');
    if (!ctxStr) throw new Error('迭代数据不存在: ' + name);

    var ctx = JSON.parse(ctxStr);
    var stage = getEffectiveStage(ctx);
    var devType = ctx.dev_type || '-';
    var reviewMode = ctx.review_mode || '';

    // 确定文档列表
    var applicableStages;
    if (devType === '新功能') {
        applicableStages = ['init', 'discuss', 'design', 'coding', 'review-and-fix', 'summarize'];
    } else {
        applicableStages = ['init', 'design', 'coding', 'review-and-fix', 'summarize'];
    }

    // 读取阶段文档
    var stageDocuments = {};
    var FILE_STAGE_MAP = {
        'prd.md': 'discuss',
        'coding-plan.md': 'design',
        'task-progress.md': 'coding',
        'review-status.md': 'review-and-fix',
        'summary.md': 'summarize'
    };

    for (var i = 0; i < applicableStages.length; i++) {
        var s = applicableStages[i];
        var docDef = STAGE_DOCUMENT_MAP[s];
        if (!docDef || !docDef.filename) {
            stageDocuments[s] = null;
            continue;
        }
        try {
            var content = await githubFileContent(basePath + '/' + docDef.filename);
            if (content) {
                var isReviewing = (ctx.stage === FILE_STAGE_MAP[docDef.filename] && !ctx.stage_completed);
                stageDocuments[s] = {
                    filename: docDef.filename,
                    content: content,
                    is_reviewing: isReviewing,
                    stage: s
                };
            } else {
                stageDocuments[s] = null;
            }
        } catch (e) {
            stageDocuments[s] = null;
        }
    }

    // 解析子任务和验收标准
    var taskProgressMd = stageDocuments['coding'] ? stageDocuments['coding'].content : null;
    var subtasks = parseSubtasks(taskProgressMd);

    var specContent = null;
    if (stageDocuments['discuss']) specContent = stageDocuments['discuss'].content;
    if (!specContent && stageDocuments['design']) specContent = stageDocuments['design'].content;
    var acceptanceCriteria = parseAcceptanceCriteria(specContent);

    // 计算时间信息
    var stageTimes = getStageTimes(ctx, stage, devType);
    var timelineGroups = getTimelineGroups(ctx, stage, devType);

    // 构建占位文案映射
    var stagePlaceholders = {};
    for (var key in STAGE_DOCUMENT_MAP) {
        if (key === 'review-and-fix' && reviewMode === 'lightweight') {
            stagePlaceholders[key] = '轻量模式，跳过自检评审';
        } else {
            stagePlaceholders[key] = STAGE_DOCUMENT_MAP[key].placeholder;
        }
    }

    return {
        name: name,
        path: '',
        dev_type: devType,
        description: ctx.description || '-',
        github_issue: ctx.github_issue || '',
        github_issue_title: ctx.github_issue_title || '',
        github_issue_url: ctx.github_issue_url || '',
        created_at: formatDatetime(ctx.created_at),
        stage: stage,
        stage_completed: ctx.stage_completed || false,
        stage_label: STAGE_LABELS[stage] || stage,
        stage_documents: stageDocuments,
        stage_placeholders: stagePlaceholders,
        subtasks: subtasks.map(function(st) {
            return { index: st.index, name: st.name, module: st.module, status: st.status };
        }),
        acceptance_criteria: acceptanceCriteria,
        stage_times: stageTimes,
        timeline_groups: timelineGroups,
        is_archived: true
    };
}

// ========================
// 6. 渲染层
// ========================

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderModeIndicator() {
    var el = document.getElementById('modeIndicator');
    if (!el) return;
    var modeClass = CONFIG.mode === 'live' ? 'mode-live' : 'mode-static';
    var modeText = CONFIG.mode === 'live' ? 'LIVE' : 'STATIC';
    el.innerHTML = '<span class="mode-indicator ' + modeClass + '">' +
        '<span class="mode-indicator-dot"></span>' + modeText + '</span>';
}

function renderListPage(iterations) {
    // 统计
    var discussing = 0, developing = 0, completed = 0;
    var discussingStages = { init: 1, discuss: 1, design: 1 };
    var developingStages = { coding: 1, 'review-and-fix': 1 };
    var completedStages = { summarize: 1, done: 1 };

    for (var i = 0; i < iterations.length; i++) {
        var s = iterations[i].stage;
        if (discussingStages[s]) discussing++;
        else if (developingStages[s]) developing++;
        else if (completedStages[s]) completed++;
    }

    document.getElementById('statDiscussing').textContent = discussing;
    document.getElementById('statDeveloping').textContent = developing;
    document.getElementById('statCompleted').textContent = completed;

    // 表格
    var tbody = document.getElementById('worktreeTableBody');
    var rows = '';
    for (var i = 0; i < iterations.length; i++) {
        var wt = iterations[i];
        var typeBadge = '';
        if (wt.dev_type && wt.dev_type !== '-') {
            typeBadge = '<span class="type-badge type-' + escapeHtml(wt.dev_type) + '">' + escapeHtml(wt.dev_type) + '</span>';
        }
        if (wt.is_archived) {
            typeBadge += '<span class="type-badge type-archived">已归档</span>';
        }

        var progressHtml;
        if (wt.subtask_total > 0) {
            var pct = Math.round(wt.subtask_completed / wt.subtask_total * 100);
            progressHtml = '<div class="progress-bar"><div class="progress-fill" style="width:' + pct + '%"></div></div>' +
                '<span class="progress-text">' + wt.subtask_completed + '/' + wt.subtask_total + '</span>';
        } else {
            progressHtml = '<span class="progress-text">-</span>';
        }

        var actionHtml;
        if (CONFIG.mode === 'static') {
            actionHtml = '<button class="delete-btn disabled-static" disabled title="静态模式">&#x2715;</button>';
        } else {
            actionHtml = '<button class="delete-btn" onclick="openCleanupModal(\'' + escapeHtml(wt.name) + '\')" title="清理">&#x2715;</button>';
        }

        rows += '<tr>' +
            '<td class="branch-name">' + typeBadge +
                '<a href="#/detail/' + encodeURIComponent(wt.name) + '" class="branch-link">' + escapeHtml(wt.name) + '</a></td>' +
            '<td class="stage-cell"><span class="stage-badge stage-' + escapeHtml(wt.stage) + '">' + escapeHtml(wt.stage_label || STAGE_LABELS[wt.stage] || wt.stage) + '</span></td>' +
            '<td class="progress-cell">' + progressHtml + '</td>' +
            '<td class="description">' + escapeHtml(wt.summary || wt.description) + '</td>' +
            '<td class="updated-at">' + escapeHtml(wt.created_at) + '</td>' +
            '<td class="actions-cell">' + actionHtml + '</td>' +
        '</tr>';
    }
    tbody.innerHTML = rows;

    // Static 模式下禁用创建按钮
    var createBtn = document.getElementById('createBtnMain');
    if (CONFIG.mode === 'static') {
        createBtn.classList.add('disabled-static');
        createBtn.setAttribute('disabled', 'disabled');
    }
}

function renderDetailPage(data) {
    // 标题
    var titleHtml = '';
    if (data.dev_type && data.dev_type !== '-') {
        titleHtml += '<span class="type-badge type-' + escapeHtml(data.dev_type) + '">' + escapeHtml(data.dev_type) + '</span> ';
    }
    titleHtml += escapeHtml(data.name);
    document.getElementById('detailTitle').innerHTML = titleHtml;

    // 操作按钮
    var actionsEl = document.getElementById('detailActions');
    if (CONFIG.mode === 'static' || data.is_archived) {
        actionsEl.innerHTML =
            '<button class="attach-btn disabled" disabled title="' + (data.is_archived ? '已归档' : '静态模式') + '">进入开发空间</button>' +
            '<button class="cleanup-btn" disabled title="' + (data.is_archived ? '已归档' : '静态模式') + '">删除开发空间</button>';
    } else {
        actionsEl.innerHTML =
            '<button class="attach-btn" id="attachBtn" onclick="attachDevspace(\'' + escapeHtml(data.name) + '\')">进入开发空间</button>' +
            '<button class="cleanup-btn" onclick="openCleanupModal(\'' + escapeHtml(data.name) + '\')">删除开发空间</button>';
    }

    // 流程进度
    renderStageProgress(data);

    // 基本信息
    var infoHtml = '';
    infoHtml += '<div class="detail-row"><span class="detail-label">工作概要</span><span class="detail-value">' + escapeHtml(data.description) + '</span></div>';
    if (data.path) {
        infoHtml += '<div class="detail-row"><span class="detail-label">分支路径</span><span class="detail-value detail-mono">' + escapeHtml(data.path) + '</span></div>';
    }
    infoHtml += '<div class="detail-row"><span class="detail-label">GitHub Issue</span><span class="detail-value">';
    if (data.github_issue) {
        infoHtml += '<a href="' + escapeHtml(data.github_issue_url) + '" target="_blank">' + escapeHtml(data.github_issue) + '</a>';
        if (data.github_issue_title) {
            infoHtml += '<span class="issue-title">' + escapeHtml(data.github_issue_title) + '</span>';
        }
    } else {
        infoHtml += '-';
    }
    infoHtml += '</span></div>';
    infoHtml += '<div class="detail-row"><span class="detail-label">创建时间</span><span class="detail-value">' + escapeHtml(data.created_at) + '</span></div>';
    document.getElementById('detailInfo').innerHTML = infoHtml;

    // 子任务
    renderSubtasks(data);

    // 阶段文档
    renderStageDocuments(data);
}

function renderStageProgress(data) {
    var wrapper = document.getElementById('stageProgressWrapper');
    var stageTimes = data.stage_times || [];
    var timelineGroups = data.timeline_groups || [];
    var currentStage = data.stage;
    var devType = data.dev_type || '';
    var isNonFeature = devType !== '新功能';

    if (stageTimes.length === 0) {
        wrapper.innerHTML = '<div class="empty-state"><span class="empty-text">暂无阶段数据</span></div>';
        return;
    }

    var html = '';

    // 分组 Header
    if (timelineGroups.length > 0) {
        html += '<div class="stage-group-header ' + (isNonFeature ? 'bugfix-mode' : '') + '">';
        for (var g = 0; g < timelineGroups.length; g++) {
            var group = timelineGroups[g];
            var groupType = (g === 1) ? 'group-core' : 'group-auxiliary';
            var groupState = '';
            if (group.is_completed) groupState = 'completed';
            else if (group.is_current) groupState = 'current';

            html += '<div class="stage-group-cell ' + groupType + ' ' + groupState + '">' +
                '<span class="group-name">' + escapeHtml(group.name) + '</span>' +
                '<span class="group-duration ' + (group.duration_display === '进行中' ? 'in-progress' : '') + '">' +
                escapeHtml(group.duration_display) + '</span></div>';
        }
        html += '</div>';
    }

    // 详细流程步骤
    html += '<div class="stage-progress ' + (isNonFeature ? 'bugfix-mode' : '') + '">';
    for (var i = 0; i < stageTimes.length; i++) {
        var st = stageTimes[i];
        var itemClass = '';
        if (st.stage === currentStage) itemClass = 'active';
        else if (st.is_completed) itemClass = 'completed';
        itemClass += st.is_core ? ' core' : ' auxiliary';

        html += '<div class="stage-item ' + itemClass + '" data-stage="' + st.stage + '" onclick="selectStage(\'' + st.stage + '\')">';
        html += '<div class="stage-circle"></div>';
        html += '<div class="stage-info">';
        html += '<span class="stage-label">' + escapeHtml(st.label) + '</span>';
        if (st.roles || st.duration_display) {
            html += '<span class="stage-meta">';
            if (st.roles) html += '<span class="stage-roles" title="' + escapeHtml(st.role_desc) + '">' + st.roles + '</span>';
            if (st.duration_display) html += '<span class="stage-duration ' + (st.duration_display === '进行中' ? 'in-progress' : '') + '">' + escapeHtml(st.duration_display) + '</span>';
            html += '</span>';
        }
        html += '</div></div>';

        // 连接线
        if (i < stageTimes.length - 1) {
            var connClass = st.is_core ? 'core' : 'auxiliary';
            if (st.is_completed) connClass += ' completed';
            html += '<div class="stage-connector ' + connClass + '"></div>';
        }
    }
    html += '</div>';

    wrapper.innerHTML = html;
}

function renderSubtasks(data) {
    var el = document.getElementById('detailSubtasks');
    var subtasks = data.subtasks || [];
    var acceptance = data.acceptance_criteria || [];

    if (subtasks.length === 0 && acceptance.length === 0) {
        el.innerHTML = '<div class="empty-state"><span class="empty-text">暂无子任务</span></div>';
        return;
    }

    var html = '';
    if (subtasks.length > 0) {
        html += '<div class="subtask-list">';
        for (var i = 0; i < subtasks.length; i++) {
            var st = subtasks[i];
            var statusIcon = st.status === '已完成' ? '&#x2713;' : (st.status === '当前' ? '&#x25B6;' : '&#x25CB;');
            html += '<div class="subtask-item subtask-' + escapeHtml(st.status) + '">' +
                '<span class="subtask-status">' + statusIcon + '</span>' +
                '<span class="subtask-name">' + escapeHtml(st.name) + '</span>' +
                '<span class="subtask-module">' + escapeHtml(st.module) + '</span>' +
                '</div>';
        }
        html += '</div>';
    }

    if (acceptance.length > 0) {
        html += '<div class="acceptance-section"><h4 class="acceptance-title">验收标准</h4><ul class="acceptance-list">';
        for (var i = 0; i < acceptance.length; i++) {
            html += '<li>' + escapeHtml(acceptance[i]) + '</li>';
        }
        html += '</ul></div>';
    }

    el.innerHTML = html;
}

function renderStageDocuments(data) {
    var viewer = document.getElementById('stageDocumentViewer');
    var docs = data.stage_documents || {};
    var placeholders = data.stage_placeholders || {};
    var currentStage = data.stage;

    var html = '';
    var stageNames = Object.keys(docs);

    for (var i = 0; i < stageNames.length; i++) {
        var stageName = stageNames[i];
        var doc = docs[stageName];

        html += '<div class="stage-document-panel" id="doc-' + stageName + '" style="display:none;">';
        if (doc) {
            html += '<div class="stage-document-header">' +
                '<div class="stage-document-header-left">' +
                '<span class="stage-file">' + escapeHtml(doc.filename) + '</span>';
            if (doc.is_reviewing) html += '<span class="reviewing-badge">评审中</span>';
            html += '</div>' +
                '<button class="expand-btn" onclick="openDocumentModal(\'' + stageName + '\')" title="全屏查看">' +
                '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">' +
                '<path d="M2 6V2H6M14 6V2H10M2 10V14H6M14 10V14H10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>' +
                '</svg></button></div>';
            html += '<div class="stage-document-body" data-stage="' + stageName + '">' +
                '<div class="markdown-body">' + (typeof marked !== 'undefined' ? marked.parse(doc.content) : '<pre>' + escapeHtml(doc.content) + '</pre>') + '</div></div>';
        } else {
            html += '<div class="empty-state"><span class="empty-text">' + escapeHtml(placeholders[stageName] || '尚未生成文档') + '</span></div>';
        }
        html += '</div>';
    }

    viewer.innerHTML = html;

    // 收集文档数据用于全屏弹窗
    window._stageDocuments = {};
    for (var i = 0; i < stageNames.length; i++) {
        var sn = stageNames[i];
        var panel = document.getElementById('doc-' + sn);
        if (!panel) continue;
        var body = panel.querySelector('.stage-document-body');
        if (!body) continue;
        var header = panel.querySelector('.stage-document-header');
        var filename = header ? header.querySelector('.stage-file') : null;
        var badge = header ? header.querySelector('.reviewing-badge') : null;
        window._stageDocuments[sn] = {
            html: body.innerHTML,
            filename: filename ? filename.textContent : '',
            isReviewing: !!badge
        };
    }

    // 默认选中当前阶段
    var initialStage = (currentStage === 'done') ? 'summarize' : currentStage;
    selectStage(initialStage);
}

// ========================
// 7. 页面交互
// ========================

var currentSelectedStage = '';

function selectStage(stageName) {
    document.querySelectorAll('.stage-document-panel').forEach(function(p) { p.style.display = 'none'; });
    var panel = document.getElementById('doc-' + stageName);
    if (panel) panel.style.display = 'block';

    document.querySelectorAll('#stageProgressWrapper .stage-item').forEach(function(i) { i.classList.remove('selected'); });
    var item = document.querySelector('#stageProgressWrapper .stage-item[data-stage="' + stageName + '"]');
    if (item) item.classList.add('selected');

    currentSelectedStage = stageName;
}

// 文档全屏弹窗
function openDocumentModal(stageName) {
    var doc = window._stageDocuments && window._stageDocuments[stageName];
    if (!doc) return;
    document.getElementById('modalFilename').textContent = doc.filename;
    var badge = document.getElementById('modalReviewingBadge');
    badge.style.display = doc.isReviewing ? 'inline-block' : 'none';
    document.getElementById('modalDocumentBody').innerHTML = doc.html;
    document.getElementById('documentModal').classList.add('show');
    document.body.style.overflow = 'hidden';
}

function closeDocumentModal() {
    document.getElementById('documentModal').classList.remove('show');
    document.body.style.overflow = '';
}

// 错误横幅
function showErrorBanner(msg) {
    document.getElementById('errorBannerText').textContent = msg;
    document.getElementById('errorBanner').style.display = 'flex';
}

function closeErrorBanner() {
    document.getElementById('errorBanner').style.display = 'none';
}

// ========================
// 8. 路由
// ========================

async function handleRoute() {
    var hash = location.hash || '#/';

    if (hash.startsWith('#/detail/')) {
        var name = decodeURIComponent(hash.slice(9));
        await showDetailPage(name);
    } else {
        await showListPage();
    }
}

async function showListPage() {
    document.getElementById('page-list').style.display = 'block';
    document.getElementById('page-detail').style.display = 'none';
    document.getElementById('loading').classList.remove('hidden');
    document.title = 'Devpipe Dashboard';

    try {
        var iterations = await fetchIterations();
        renderModeIndicator();
        renderListPage(iterations);
    } catch (e) {
        showErrorBanner(e.message || '加载失败');
    } finally {
        document.getElementById('loading').classList.add('hidden');
    }
}

async function showDetailPage(name) {
    document.getElementById('page-list').style.display = 'none';
    document.getElementById('page-detail').style.display = 'block';
    document.getElementById('loading').classList.remove('hidden');
    document.title = name + ' - Devpipe Dashboard';

    try {
        var data = await fetchIterationDetail(name);
        renderDetailPage(data);
    } catch (e) {
        showErrorBanner(e.message || '加载详情失败');
    } finally {
        document.getElementById('loading').classList.add('hidden');
    }
}

window.addEventListener('hashchange', handleRoute);
window.addEventListener('DOMContentLoaded', handleRoute);

// ========================
// 9. Flask 模式专属交互
// ========================

// --- 进入开发空间 ---
function attachDevspace(branchName) {
    if (CONFIG.mode === 'static') return;
    var btn = document.getElementById('attachBtn');
    if (!btn || btn.disabled) return;

    var originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '连接中...';
    btn.classList.add('loading');

    fetch('/api/devspace/attach', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch_name: branchName })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        btn.classList.remove('loading');
        if (data.success) {
            btn.textContent = '已打开';
            btn.classList.add('success');
            setTimeout(function() {
                btn.textContent = originalText;
                btn.classList.remove('success');
                btn.disabled = false;
            }, 2000);
        } else {
            btn.textContent = data.error || '连接失败';
            btn.classList.add('error');
            setTimeout(function() {
                btn.textContent = originalText;
                btn.classList.remove('error');
                btn.disabled = false;
            }, 3000);
        }
    })
    .catch(function() {
        btn.classList.remove('loading');
        btn.textContent = '网络错误';
        btn.classList.add('error');
        setTimeout(function() {
            btn.textContent = originalText;
            btn.classList.remove('error');
            btn.disabled = false;
        }, 3000);
    });
}

// --- 创建开发空间向导 ---
var createState = {
    currentStep: 1,
    issueData: null,
    issueQueried: false,
    lastQueriedIssue: '',
    branchValidated: false,
    branchPrefix: 'feature-',
    taskId: null,
    pollTimer: null,
    isLoading: false
};

function openCreateModal() {
    if (CONFIG.mode === 'static') return;
    document.getElementById('createModal').classList.add('show');
    resetWizard();
}

function closeCreateModal() {
    document.getElementById('createModal').classList.remove('show');
    if (createState.pollTimer) {
        clearInterval(createState.pollTimer);
        createState.pollTimer = null;
    }
}

function resetWizard() {
    createState.currentStep = 1;
    createState.issueData = null;
    createState.issueQueried = false;
    createState.lastQueriedIssue = '';
    createState.branchValidated = false;
    createState.branchPrefix = 'feature-';
    createState.taskId = null;
    createState.isLoading = false;

    document.getElementById('issueInput').value = '';
    document.getElementById('baseBranch').value = 'main';
    document.getElementById('branchMode').value = 'remote';
    document.getElementById('devType').value = '';
    document.getElementById('description').value = '';
    document.getElementById('branchName').value = '';

    document.getElementById('issueStatus').textContent = '';
    document.getElementById('issueStatus').className = 'field-status';
    document.getElementById('issueResult').classList.add('hidden');
    document.getElementById('branchStatus').textContent = '';
    document.getElementById('branchStatus').className = 'field-status';
    document.getElementById('branchNameStatus').textContent = '';
    document.getElementById('branchNameStatus').className = 'field-status';
    document.getElementById('branchPrefix').textContent = 'feature-';
    document.getElementById('devTypeHint').textContent = '自动从 GitHub Issue类型推断';
    document.getElementById('devTypeDisplay').textContent = '-';
    document.getElementById('descriptionDisplay').textContent = '-';
    document.getElementById('issueBodyDisplay').textContent = '-';

    document.getElementById('createProgressFill').style.width = '0%';
    document.getElementById('createPercent').textContent = '0%';
    document.getElementById('createStage').textContent = '准备中...';
    document.getElementById('createStages').innerHTML = '';
    document.getElementById('createLogs').textContent = '';
    document.getElementById('createResult').classList.add('hidden');
    var rs = document.querySelector('#createModal .result-success');
    if (rs) rs.classList.add('hidden');
    var re = document.querySelector('#createModal .result-error');
    if (re) re.classList.add('hidden');

    updateStepDisplay();
}

function updateStepDisplay() {
    document.querySelectorAll('#createModal .wizard-step').forEach(function(el) {
        var step = parseInt(el.dataset.step);
        el.classList.remove('active', 'completed');
        if (step === createState.currentStep) el.classList.add('active');
        else if (step < createState.currentStep) el.classList.add('completed');
    });

    document.querySelectorAll('#createModal .wizard-panel').forEach(function(el) {
        el.classList.remove('active');
        if (parseInt(el.dataset.step) === createState.currentStep) el.classList.add('active');
    });

    var btnPrev = document.getElementById('btnPrev');
    var btnNext = document.getElementById('btnNext');
    var btnCreate = document.getElementById('btnCreate');
    var btnDone = document.getElementById('btnDone');

    btnPrev.style.display = createState.currentStep > 1 && createState.currentStep < 4 ? 'inline-block' : 'none';
    btnNext.style.display = createState.currentStep < 3 ? 'inline-block' : 'none';
    btnCreate.style.display = createState.currentStep === 3 ? 'inline-block' : 'none';
    btnDone.style.display = createState.currentStep === 4 && (createState.taskId === null || !document.getElementById('createResult').classList.contains('hidden')) ? 'inline-block' : 'none';
}

async function nextStep() {
    if (createState.isLoading) return;
    if (createState.currentStep === 1) {
        if (!(await validateStep1Async())) return;
    } else if (createState.currentStep === 2) {
        if (!(await validateStep2Async())) return;
        updateCreateSummary();
    }
    createState.currentStep++;
    updateStepDisplay();
}

function prevStep() {
    if (createState.currentStep > 1) {
        createState.currentStep--;
        updateStepDisplay();
    }
}

function setButtonLoading(loading) {
    createState.isLoading = loading;
    var btnNext = document.getElementById('btnNext');
    if (loading) {
        btnNext.disabled = true;
        btnNext.textContent = '验证中...';
    } else {
        btnNext.disabled = false;
        btnNext.textContent = '下一步';
    }
}

function showFieldStatus(elementId, message, type) {
    var el = document.getElementById(elementId);
    el.textContent = message;
    el.className = 'field-status ' + type;
}

async function validateStep1Async() {
    var issueInput = document.getElementById('issueInput').value.trim();
    if (!issueInput) {
        showFieldStatus('issueStatus', '请输入 GitHub Issue ID', 'error');
        return false;
    }
    setButtonLoading(true);
    try {
        if (!createState.issueQueried || createState.lastQueriedIssue !== issueInput) {
            if (!(await queryGitHubIssueAsync())) { setButtonLoading(false); return false; }
        }
        var baseBranch = document.getElementById('baseBranch').value.trim();
        if (!baseBranch) {
            showFieldStatus('branchStatus', '请输入基础分支', 'error');
            setButtonLoading(false);
            return false;
        }
        if (!createState.branchValidated) {
            if (!(await validateBaseBranchAsync())) { setButtonLoading(false); return false; }
        }
        setButtonLoading(false);
        return true;
    } catch (e) {
        setButtonLoading(false);
        return false;
    }
}

async function validateStep2Async() {
    var devType = document.getElementById('devType').value;
    var desc = document.getElementById('description').value.trim();
    if (!devType || !desc) {
        showFieldStatus('devTypeHint', 'GitHub Issue信息不完整，请返回上一步', 'error');
        return false;
    }
    setButtonLoading(true);
    try {
        if (!(await generateBranchNameAsync())) { setButtonLoading(false); return false; }
        await checkBranchConflicts();
        setButtonLoading(false);
        return true;
    } catch (e) {
        setButtonLoading(false);
        return false;
    }
}

async function queryGitHubIssueAsync() {
    var issueVal = document.getElementById('issueInput').value.trim();
    if (!issueVal) { showFieldStatus('issueStatus', '请输入 Issue 编号', 'error'); return false; }
    showFieldStatus('issueStatus', '查询中...', 'loading');
    try {
        var resp = await fetch('/api/github/issue', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ issue_input: issueVal })
        });
        var result = await resp.json();
        if (result.success) {
            var allowedTypes = [/^新功能$/, /^bugfix$/i, /^优化重构$/];
            var cardType = result.data.dev_type || '';
            var isAllowed = allowedTypes.some(function(p) { return p.test(cardType); });
            if (!isAllowed) {
                createState.issueData = null;
                createState.issueQueried = false;
                createState.lastQueriedIssue = '';
                showFieldStatus('issueStatus', '不支持的Issue 类型"' + cardType + '"，仅支持 新功能/Bugfix/优化重构', 'error');
                document.getElementById('issueResult').classList.add('hidden');
                return false;
            }
            createState.issueData = result.data;
            createState.issueQueried = true;
            createState.lastQueriedIssue = issueVal;
            showFieldStatus('issueStatus', '查询成功', 'success');

            var LABEL_PREFIX = { feature: 'feature-', bug: 'fix-', refactor: 'refactor-' };
            var labels = result.data.labels || [];
            var prefix = 'feature-';
            for (var i = 0; i < labels.length; i++) {
                if (LABEL_PREFIX[labels[i]]) { prefix = LABEL_PREFIX[labels[i]]; break; }
            }
            createState.branchPrefix = prefix;
            document.getElementById('branchPrefix').textContent = prefix;

            var resultEl = document.getElementById('issueResult');
            resultEl.classList.remove('hidden');
            resultEl.querySelector('.dev-type').textContent = result.data.dev_type;
            resultEl.querySelector('.issue-title').textContent = result.data.title;

            if (result.data.dev_type) {
                document.getElementById('devType').value = result.data.dev_type;
                document.getElementById('devTypeDisplay').textContent = result.data.dev_type;
                showFieldStatus('devTypeHint', '根据Issue 类型"' + result.data.dev_type + '"自动选择', 'info');
            }
            if (result.data.title) {
                document.getElementById('description').value = result.data.title;
                document.getElementById('descriptionDisplay').textContent = result.data.title;
            }
            if (result.data.body) {
                document.getElementById('issueBodyDisplay').textContent = result.data.body;
            }
            return true;
        } else {
            createState.issueData = null;
            createState.issueQueried = false;
            createState.lastQueriedIssue = '';
            showFieldStatus('issueStatus', result.error || '查询失败', 'error');
            document.getElementById('issueResult').classList.add('hidden');
            return false;
        }
    } catch (e) {
        showFieldStatus('issueStatus', '网络错误', 'error');
        return false;
    }
}

async function validateBaseBranchAsync() {
    var branch = document.getElementById('baseBranch').value.trim();
    var mode = document.getElementById('branchMode').value;
    if (!branch) { showFieldStatus('branchStatus', '请输入分支名', 'error'); return false; }
    showFieldStatus('branchStatus', '验证中...', 'loading');
    try {
        var resp = await fetch('/api/branch/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ branch: branch, mode: mode })
        });
        var result = await resp.json();
        if (result.success && result.exists) {
            createState.branchValidated = true;
            showFieldStatus('branchStatus', '分支存在', 'success');
            return true;
        } else {
            createState.branchValidated = false;
            showFieldStatus('branchStatus', result.error || '分支不存在', 'error');
            return false;
        }
    } catch (e) {
        showFieldStatus('branchStatus', '网络错误', 'error');
        return false;
    }
}

async function generateBranchNameAsync() {
    var desc = document.getElementById('description').value.trim();
    if (!desc) { showFieldStatus('branchNameStatus', '描述为空', 'error'); return false; }
    showFieldStatus('branchNameStatus', '生成分支名...', 'loading');
    try {
        var resp = await fetch('/api/devspace/suggest-branch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description: desc })
        });
        var result = await resp.json();
        if (result.success) {
            document.getElementById('branchName').value = result.branch_name;
            showFieldStatus('branchNameStatus', '', 'info');
            return true;
        }
    } catch (e) { /* fallback */ }
    var ts = new Date().toISOString().slice(5, 16).replace(/[-:T]/g, '');
    document.getElementById('branchName').value = 'dev-' + ts;
    showFieldStatus('branchNameStatus', '使用默认分支名', 'info');
    return true;
}

function regenerateBranchName() {
    generateBranchNameAsync().then(function() { checkBranchConflicts(); });
}

async function checkBranchConflicts() {
    var branchDesc = document.getElementById('branchName').value.trim();
    if (!branchDesc) return;
    var fullName = createState.branchPrefix + branchDesc;
    try {
        var resp = await fetch('/api/devspace/check-conflicts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ branch_name: fullName })
        });
        var result = await resp.json();
        if (result.success && result.conflicts.length === 0) {
            showFieldStatus('branchNameStatus', '分支名可用', 'success');
        } else if (result.success && result.conflicts.length > 0) {
            showFieldStatus('branchNameStatus', '存在冲突: ' + result.conflicts[0], 'error');
        }
    } catch (e) { /* ignore */ }
}

function updateCreateSummary() {
    document.getElementById('summaryIssue').textContent = createState.issueData ? createState.issueData.number : '-';
    document.getElementById('summaryBaseBranch').textContent = document.getElementById('baseBranch').value || 'main';
    document.getElementById('summaryDevType').textContent = document.getElementById('devType').value || '-';
    var branchDesc = document.getElementById('branchName').value || '';
    document.getElementById('summaryBranchName').textContent = branchDesc ? createState.branchPrefix + branchDesc : '-';
    document.getElementById('summaryDescription').textContent = document.getElementById('description').value || '-';
}

async function startCreate() {
    if (CONFIG.mode === 'static') return;
    var branchDesc = document.getElementById('branchName').value.trim();
    var baseBranch = document.getElementById('baseBranch').value.trim();
    var mode = document.getElementById('branchMode').value;
    var devType = document.getElementById('devType').value;
    var desc = document.getElementById('description').value.trim();
    var branchName = createState.branchPrefix + branchDesc;

    if (!branchDesc) { showFieldStatus('branchNameStatus', '请输入分支名描述部分', 'error'); return; }

    createState.currentStep = 4;
    updateStepDisplay();
    initCreateStagesDisplay();

    try {
        var resp = await fetch('/api/devspace/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                branch_name: branchName,
                base_branch: baseBranch,
                mode: mode,
                github_issue: createState.issueData ? createState.issueData.number : null,
                github_issue_title: createState.issueData ? createState.issueData.title : null,
                github_issue_body: createState.issueData ? createState.issueData.body : undefined,
                github_issue_url: createState.issueData ? createState.issueData.url : undefined,
                github_repo: createState.issueData ? createState.issueData.repo : null,
                dev_type: devType,
                description: desc
            })
        });
        var result = await resp.json();
        if (result.success) {
            createState.taskId = result.task_id;
            pollCreateTaskStatus();
        } else {
            showCreateError(result.error || '创建失败');
        }
    } catch (e) {
        showCreateError('网络错误: ' + e.message);
    }
}

function initCreateStagesDisplay() {
    var stages = ['前置检查', '分支同步', '创建 Worktree', '构建镜像', '创建容器', '初始化 Git', '初始化配置', '创建 Tmux'];
    var container = document.getElementById('createStages');
    container.innerHTML = stages.map(function(name) {
        return '<div class="stage-item" data-stage="' + name + '"><span class="stage-status pending"></span><span class="stage-name">' + name + '</span></div>';
    }).join('');
}

async function pollCreateTaskStatus() {
    if (!createState.taskId) return;
    try {
        var resp = await fetch('/api/devspace/status/' + createState.taskId);
        var status = await resp.json();
        if (status.error && resp.status === 404) { showCreateError('任务不存在'); return; }
        document.getElementById('createProgressFill').style.width = status.progress + '%';
        document.getElementById('createPercent').textContent = status.progress + '%';
        document.getElementById('createStage').textContent = status.stage || '进行中...';
        if (status.stages) {
            status.stages.forEach(function(stage) {
                var el = document.querySelector('#createStages .stage-item[data-stage="' + stage.name + '"] .stage-status');
                if (el) el.className = 'stage-status ' + stage.status;
            });
        }
        if (status.logs && status.logs.length > 0) {
            document.getElementById('createLogs').textContent = status.logs.join('\n');
        }
        if (status.status === 'success') { showCreateSuccess(status.result); return; }
        if (status.status === 'failed') { showCreateError(status.error, status.cleaned_up); return; }
        createState.pollTimer = setTimeout(pollCreateTaskStatus, 1000);
    } catch (e) {
        createState.pollTimer = setTimeout(pollCreateTaskStatus, 2000);
    }
}

function showCreateSuccess(result) {
    document.getElementById('createResult').classList.remove('hidden');
    document.querySelector('#createModal .result-success').classList.remove('hidden');
    document.getElementById('resultCommand').textContent = 'tmux attach -t ' + result.tmux_session;
    document.getElementById('btnDone').style.display = 'inline-block';
    document.getElementById('createProgressFill').style.width = '100%';
    document.getElementById('createPercent').textContent = '100%';
    document.getElementById('createStage').textContent = '完成';
}

function showCreateError(error, cleanedUp) {
    document.getElementById('createResult').classList.remove('hidden');
    document.querySelector('#createModal .result-error').classList.remove('hidden');
    document.getElementById('resultError').textContent = error;
    if (cleanedUp) {
        var hint = document.querySelector('#createModal .result-hint');
        if (hint) hint.textContent = '已自动清理资源，可修改参数后重新创建';
    }
    document.getElementById('btnDone').style.display = 'inline-block';
    document.getElementById('createProgressFill').classList.add('error');
}

function toggleLogs() {
    var logs = document.getElementById('createLogs');
    var btn = logs.parentElement.querySelector('.toggle-logs');
    if (logs.classList.contains('collapsed')) {
        logs.classList.remove('collapsed');
        btn.textContent = '折叠';
    } else {
        logs.classList.add('collapsed');
        btn.textContent = '展开';
    }
}

// 事件监听
document.addEventListener('DOMContentLoaded', function() {
    // 基础分支变化时重新验证
    var baseBranch = document.getElementById('baseBranch');
    var branchMode = document.getElementById('branchMode');
    if (baseBranch) {
        baseBranch.addEventListener('change', function() { createState.branchValidated = false; });
    }
    if (branchMode) {
        branchMode.addEventListener('change', function() { createState.branchValidated = false; });
    }
    var branchNameInput = document.getElementById('branchName');
    if (branchNameInput) {
        branchNameInput.addEventListener('change', checkBranchConflicts);
    }

    // Modal 关闭事件
    document.getElementById('createModal').addEventListener('click', function(e) {
        if (e.target === this) closeCreateModal();
    });
    document.getElementById('documentModal').addEventListener('click', function(e) {
        if (e.target === this) closeDocumentModal();
    });
    document.getElementById('cleanupModal').addEventListener('click', function(e) {
        if (e.target === this) closeCleanupModal(true);
    });

    // ESC 关闭
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            if (document.getElementById('documentModal').classList.contains('show')) {
                closeDocumentModal();
            } else if (document.getElementById('cleanupModal').classList.contains('show')) {
                closeCleanupModal(true);
            } else if (document.getElementById('createModal').classList.contains('show')) {
                closeCreateModal();
            }
        }
    });
});

// --- 清理开发空间弹窗 ---
var cleanupState = {
    branchName: '',
    resources: null,
    currentStep: 1,
    taskId: null,
    pollTimer: null,
    needsReload: false
};

function openCleanupModal(branchName) {
    if (CONFIG.mode === 'static') return;
    cleanupState.branchName = branchName;
    cleanupState.resources = null;
    cleanupState.currentStep = 1;
    cleanupState.taskId = null;
    cleanupState.needsReload = false;
    if (cleanupState.pollTimer) { clearInterval(cleanupState.pollTimer); cleanupState.pollTimer = null; }

    document.getElementById('cleanupBranchName').textContent = branchName;
    document.getElementById('cleanupResourceLoading').style.display = 'block';
    document.getElementById('cleanupResourceList').style.display = 'none';
    document.getElementById('cleanupNoResources').style.display = 'none';

    showCleanupStep(1);
    document.getElementById('cleanupBtnNext').style.display = 'none';
    document.getElementById('cleanupBtnForce').style.display = 'none';
    document.getElementById('cleanupBtnDone').style.display = 'none';
    document.getElementById('cleanupBtnCancel').style.display = 'inline-block';

    document.getElementById('cleanupModal').classList.add('show');
    probeResources();
}

function closeCleanupModal(checkReload) {
    document.getElementById('cleanupModal').classList.remove('show');
    if (cleanupState.pollTimer) { clearInterval(cleanupState.pollTimer); cleanupState.pollTimer = null; }
    if (checkReload && cleanupState.needsReload) {
        handleRoute();
    }
}

function showCleanupStep(step) {
    cleanupState.currentStep = step;
    document.getElementById('cleanupStep1').classList.remove('active');
    document.getElementById('cleanupStep2').classList.remove('active');
    document.getElementById('cleanupStep3').classList.remove('active');
    document.getElementById('cleanupStep' + step).classList.add('active');
}

async function probeResources() {
    try {
        var resp = await fetch('/api/devspace/probe-resources', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ branch_name: cleanupState.branchName })
        });
        var result = await resp.json();
        document.getElementById('cleanupResourceLoading').style.display = 'none';
        if (!result.success) {
            document.getElementById('cleanupResourceList').innerHTML = '<div class="field-status error">探测失败: ' + (result.error || '未知错误') + '</div>';
            document.getElementById('cleanupResourceList').style.display = 'block';
            return;
        }
        cleanupState.resources = result.data;
        renderResourceList(result.data);
        if (result.data.total_count === 0) {
            document.getElementById('cleanupNoResources').style.display = 'block';
            document.getElementById('cleanupBtnNext').style.display = 'none';
        } else {
            document.getElementById('cleanupBtnNext').style.display = 'inline-block';
        }
    } catch (e) {
        document.getElementById('cleanupResourceLoading').style.display = 'none';
        document.getElementById('cleanupResourceList').innerHTML = '<div class="field-status error">网络错误</div>';
        document.getElementById('cleanupResourceList').style.display = 'block';
    }
}

function renderResourceList(data) {
    var items = [
        { key: 'container', label: 'Docker 容器', detail: data.container.name },
        { key: 'volume', label: 'Docker 存储卷', detail: data.volume.name },
        { key: 'tmux', label: 'Tmux 终端', detail: data.tmux.name },
        { key: 'worktree', label: 'Worktree 目录', detail: data.worktree.path },
        { key: 'branch', label: 'Git 分支', detail: data.branch.name }
    ];
    var html = items.map(function(item) {
        var exists = data[item.key].exists;
        return '<div class="resource-item ' + (exists ? 'exists' : 'missing') + '">' +
            '<span class="resource-icon">' + (exists ? '&#x2713;' : '&#x2015;') + '</span>' +
            '<span class="resource-name">' + item.label + '</span>' +
            '<span class="resource-detail">' + item.detail + '</span></div>';
    }).join('');
    var el = document.getElementById('cleanupResourceList');
    el.innerHTML = html;
    el.style.display = 'block';
}

async function proceedToCleanup() {
    if (CONFIG.mode === 'static') return;
    document.getElementById('cleanupBtnNext').style.display = 'none';
    try {
        var resp = await fetch('/api/devspace/check-changes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ branch_name: cleanupState.branchName })
        });
        var result = await resp.json();
        if (result.success && result.data.has_changes) {
            document.getElementById('cleanupChangesCode').textContent = result.data.changes;
            showCleanupStep(2);
            document.getElementById('cleanupBtnForce').style.display = 'inline-block';
            document.getElementById('cleanupBtnCancel').style.display = 'inline-block';
        } else {
            startCleanup(false);
        }
    } catch (e) {
        startCleanup(false);
    }
}

async function startCleanup(force) {
    if (CONFIG.mode === 'static') return;
    showCleanupStep(3);
    document.getElementById('cleanupBtnNext').style.display = 'none';
    document.getElementById('cleanupBtnForce').style.display = 'none';
    document.getElementById('cleanupBtnCancel').style.display = 'none';

    initCleanupStagesDisplay();
    document.getElementById('cleanupProgressFill').style.width = '0%';
    document.getElementById('cleanupProgressFill').className = 'create-progress-fill';
    document.getElementById('cleanupPercent').textContent = '0%';
    document.getElementById('cleanupStage').textContent = '准备中...';
    document.getElementById('cleanupLogs').textContent = '';
    document.getElementById('cleanupResult').classList.add('hidden');
    document.getElementById('cleanupResultSuccess').classList.add('hidden');
    document.getElementById('cleanupResultError').classList.add('hidden');

    try {
        var resp = await fetch('/api/devspace/cleanup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ branch_name: cleanupState.branchName, force: force })
        });
        var result = await resp.json();
        if (result.success) {
            cleanupState.taskId = result.task_id;
            cleanupState.needsReload = true;
            pollCleanupStatus();
        } else {
            showCleanupError(result.error || '清理失败');
        }
    } catch (e) {
        showCleanupError('网络错误: ' + e.message);
    }
}

function initCleanupStagesDisplay() {
    var stages = ['停止容器', '删除存储卷', '关闭终端', '删除工作目录', '删除分支'];
    var container = document.getElementById('cleanupStages');
    container.innerHTML = stages.map(function(name) {
        return '<div class="stage-item" data-cleanup-stage="' + name + '"><span class="stage-status pending"></span><span class="stage-name">' + name + '</span></div>';
    }).join('');
}

async function pollCleanupStatus() {
    if (!cleanupState.taskId) return;
    try {
        var resp = await fetch('/api/devspace/status/' + cleanupState.taskId);
        var status = await resp.json();
        if (resp.status === 404) { showCleanupError('任务不存在'); return; }
        document.getElementById('cleanupProgressFill').style.width = status.progress + '%';
        document.getElementById('cleanupPercent').textContent = status.progress + '%';
        document.getElementById('cleanupStage').textContent = status.stage || '进行中...';
        if (status.stages) {
            status.stages.forEach(function(stage) {
                var el = document.querySelector('[data-cleanup-stage="' + stage.name + '"] .stage-status');
                if (el) el.className = 'stage-status ' + stage.status;
            });
        }
        if (status.logs && status.logs.length > 0) {
            document.getElementById('cleanupLogs').textContent = status.logs.join('\n');
        }
        if (status.status === 'success') { showCleanupSuccess(); return; }
        if (status.status === 'failed') { showCleanupError(status.error || '清理失败'); return; }
        cleanupState.pollTimer = setTimeout(pollCleanupStatus, 1000);
    } catch (e) {
        cleanupState.pollTimer = setTimeout(pollCleanupStatus, 2000);
    }
}

function showCleanupSuccess() {
    document.getElementById('cleanupResult').classList.remove('hidden');
    document.getElementById('cleanupResultSuccess').classList.remove('hidden');
    document.getElementById('cleanupProgressFill').style.width = '100%';
    document.getElementById('cleanupPercent').textContent = '100%';
    document.getElementById('cleanupStage').textContent = '完成';
    document.getElementById('cleanupBtnDone').style.display = 'inline-block';
}

function showCleanupError(error) {
    document.getElementById('cleanupResult').classList.remove('hidden');
    document.getElementById('cleanupResultError').classList.remove('hidden');
    document.getElementById('cleanupResultErrorMsg').textContent = error;
    document.getElementById('cleanupProgressFill').classList.add('error');
    document.getElementById('cleanupBtnDone').style.display = 'inline-block';
}

function toggleCleanupLogs() {
    var logs = document.getElementById('cleanupLogs');
    var btn = logs.parentElement.querySelector('.toggle-logs');
    if (logs.classList.contains('collapsed')) {
        logs.classList.remove('collapsed');
        btn.textContent = '折叠';
    } else {
        logs.classList.add('collapsed');
        btn.textContent = '展开';
    }
}
