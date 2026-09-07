/**
 * 全局样式唯一 JS 入口。
 *
 * 禁止在 CSS 文件里把 @import 写在 @tailwind 之后——浏览器会直接丢弃后续 @import，
 * 导致整站样式失效。此处通过 Vite side-effect import 严格按级联顺序加载各层 CSS。
 */
import './fonts.css';
import './tailwind.css';
import './1-settings/variables.css';
import './1-settings/breakpoints.css';
import './2-reset/base.css';
import './3-generic/keyframes.css';
import './3-generic/shared.css';
import './5-utilities/helpers.css';
import './3-generic/page-hooks.css';
import './pages/learning-path/learning-path.css';
import './4-components/layout-shell.css';
import './4-components/global-header.css';
import './4-components/ai-workspace.css';
import './4-components/panel-close.css';
import './pages/personal-settings/personal-settings.css';
import './pages/learning-profile/learning-profile.css';
import './pages/learning-calendar/learning-calendar.css';
import './4-components/scroller.css';
import './pages/assessment/assessment.css';
import './4-components/workspace-chrome.css';
import './pages/announcements/announcements.css';
import './pages/curriculum/curriculum.css';
import './pages/admin/interface-settings.css';
import './pages/admin/knowledge-base.css';
import './pages/admin/knowledge-chunk-workbench.css';
import './pages/ta/ta-workbench.css';
import './4-components/resource-generation.css';
import './4-components/workspace-theme.css';
import './4-components/workspace-palette.css';
import './4-components/overlay-transparency.css';
import './pages/admin/admin-workbench.css';
import './4-components/onboarding.css';
import './theme.css';
import './artifact-canvas.css';
import './codex-pet.css';
