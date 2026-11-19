import { desktop, mobile as mobileAreas, more, areaOf } from "./navigation.js";

const telegram = window.Telegram?.WebApp;
// Telegram includes the signed launch data in the fragment, even if the SDK fails to load.
const launchData = () => window.Telegram?.WebApp?.initData ||
  new URLSearchParams(location.hash.slice(1)).get("tgWebAppData") || "";
const proxy = document.querySelector('meta[name="killer-proxy"]').content;
const content = document.querySelector("#content");
const modal = document.querySelector("#dialog");
const modalForm = document.querySelector("#dialog-form");
const toast = document.querySelector("#toast");
let language = localStorage.getItem("killer-language") === "en" ? "en" : "fa";
let state = {section: "overview"};
let isOwner = false;
let connected = null;
let sidebarCompact = localStorage.getItem("killer-sidebar") === "compact";
let mediaPreviewUrl = null;
let revision = 0;
let notificationTimer;
let serverLanguageLoaded = false;
const cleanupSelection = new Map();
const expandedProfiles = new Map();
const cleanupProfiles = new Map();
let cleanupView = localStorage.getItem("killer-cleanup-view") === "compact" ? "compact" : "review";
let cleanupTimer;
let cleanupReportOpen = false;

const strings = {
  overview:["میز کار","Workspace"],profile:["حساب من","My account"],chats:["گفت‌وگوها","Chats"],
  dialog_profiles:["پروفایل‌ها","Profiles"],
  channels:["کانال‌ها","Channels"],groups:["گروه‌ها","Groups"],contacts:["مخاطبین","Contacts"],
  messages:["پیام‌ها","Messages"],media:["رسانه‌ها","Media"],security:["امنیت","Security"],
  analytics:["آمار","Analytics"],backups:["پشتیبان‌ها","Backups"],automation:["خودکارسازی","Automation"],
  settings:["تنظیمات","Settings"],activity:["فعالیت‌ها","Activity"],more:["بیشتر","More"],
  dialogs:["همهٔ گفت‌وگوها","All dialogs"],connected:["متصل به حساب","Account connected"],
  disconnected:["حساب متصل نیست","Account disconnected"],syncing:["در حال همگام‌سازی","Synchronizing"],
  sync:["همگام‌سازی","Sync"],quick:["دسترسی سریع","Quick actions"],recent:["فعالیت اخیر","Recent activity"],
  search:["جست‌وجو","Search"],all:["همه","All"],public:["عمومی","Public"],private:["خصوصی","Private"],
  archived:["بایگانی","Archived"],bots:["بات‌ها","Bots"],favorites:["علاقه‌مندی‌ها","Favorites"],
  tagged:["برچسب‌دار","Tagged"],folders:["پوشه‌ها","Folders"],name:["عنوان","Name"],
  recent_order:["بازدید اخیر","Recently viewed"],previous:["قبل","Previous"],next:["بعد","Next"],
  page:["صفحه","Page"],empty:["موردی پیدا نشد.","No results."],open_bot:["از دکمهٔ Mini App در گفت‌وگوی خصوصی بات وارد شوید.","Open this Mini App from the bot’s private chat."],
  loading:["در حال بارگیری…","Loading…"],failed:["درخواست ناموفق بود.","The request failed."],
  retry:["تلاش دوباره","Retry"],done:["انجام شد.","Completed."],cancel:["لغو","Cancel"],
  confirm:["تأیید","Confirm"],details:["جزئیات","Details"],back:["بازگشت","Back"],
  edit:["ویرایش","Edit"],delete:["حذف","Delete"],add:["افزودن","Add"],
  username:["نام کاربری","Username"],first_name:["نام","First name"],last_name:["نام خانوادگی","Last name"],
  about:["درباره","Bio"],id:["شناسه","ID"],phone:["تلفن","Phone"],link:["پیوند","Link"],
  members:["اعضا","Members"],unread:["خوانده‌نشده","Unread"],tag:["برچسب","Tag"],
  favorite:["افزودن علاقه‌مندی","Add favorite"],unfavorite:["حذف علاقه‌مندی","Remove favorite"],
  archive:["بایگانی کردن","Archive"],unarchive:["خارج کردن از بایگانی","Unarchive"],pin:["سنجاق","Pin"],
  unpin:["برداشتن سنجاق","Unpin"],leave:["خروج از گفت‌وگو","Leave chat"],history:["تاریخچه","History"],
  saved:["پیام‌های ذخیره‌شده","Saved Messages"],scheduled:["زمان‌بندی‌شده","Scheduled"],
  pinned:["سنجاق‌شده","Pinned"],drafts:["پیش‌نویس‌ها","Drafts"],draft:["پیش‌نویس","Draft"],
  photo:["عکس","Photo"],video:["ویدئو","Video"],file:["سند","Document"],audio:["صوت","Audio"],
  voice:["پیام صوتی","Voice message"],download:["دریافت","Download"],protected:["محتوای محافظت‌شده","Protected content"],
  devices:["دستگاه‌ها","Devices"],current:["نشست فعلی","Current session"],revoke:["پایان نشست","Terminate session"],
  two_factor:["ورود دومرحله‌ای","Two-step verification"],enabled:["فعال","Enabled"],disabled:["غیرفعال","Disabled"],
  privacy:["حریم خصوصی","Privacy"],seen:["آخرین بازدید","Last seen"],calls:["تماس‌ها","Calls"],
  invites:["دعوت‌ها","Invites"],forwards:["ارجاع پیام‌ها","Forwarded messages"],nobody:["هیچ‌کس","Nobody"],
  except_contacts:["به‌جز مخاطبین","Except contacts"],allowed_users:["کاربران مجاز","Allowed users"],
  blocked_users:["کاربران مسدود","Excluded users"],allowed_chats:["گفت‌وگوهای مجاز","Allowed chats"],
  blocked_chats:["گفت‌وگوهای مسدود","Excluded chats"],custom:["سفارشی","Custom"],
  data_source:["دادهٔ محلی، بر پایهٔ همگام‌سازی","Local data from synchronizations"],
  live:["دادهٔ زندهٔ تلگرام","Live Telegram data"],trends:["روند تعداد گفت‌وگوها","Dialog count over time"],
  distribution:["توزیع گفت‌وگوها","Dialog distribution"],storage:["حجم پایگاه داده","Database storage"],
  create_backup:["ساخت پشتیبان رمزگذاری‌شده","Create encrypted backup"],
  app_backup:["نسخهٔ پشتیبان دادهٔ برنامه. تاریخچهٔ تلگرام جداست.","Application data backup. Telegram history is separate."],
  backup_keep:["تعداد پشتیبان‌های نگهداری‌شده","Retained backups"],preview:["بررسی نسخه","Verify backup"],
  schema:["نسخهٔ پایگاه","Schema version"],export_json:["خروجی JSON","Export JSON"],export_csv:["خروجی CSV","Export CSV"],
  sync_enabled:["همگام‌سازی دوره‌ای","Periodic synchronization"],login_alerts:["هشدار نشست تازه","New-session alerts"],
  automatic_backup:["پشتیبان روزانه","Daily encrypted backup"],summary:["خلاصهٔ روزانه","Daily summary"],
  language:["زبان","Language"],invalid:["مقدار واردشده معتبر نیست.","Enter a valid value."],
  command:["جست‌وجوی فرمان","Command search"],select_peer:["گفت‌وگو را از فهرست گفت‌وگوها انتخاب کنید.","Choose a chat from the dialog list."],
  chat_detail:["جزئیات گفت‌وگو","Chat details"],search_history:["جست‌وجوهای اخیر","Recent searches"],
  clear_search:["پاک‌کردن تاریخچهٔ جست‌وجو","Clear search history"],global_search:["جست‌وجوی همه‌جانبه","Unified search"],
  after:["از تاریخ","From date"],before:["تا تاریخ","Until date"],sender:["فرستنده","Sender"],
  plugins:["افزونه‌ها","Plugins"],inactivity:["گفت‌وگوهای کم‌فعال","Inactive dialogs"],
  inactivity_report:["گزارش روزانهٔ گفت‌وگوهای کم‌فعال","Daily inactivity report"],
  shared_groups:["گروه‌های مشترک","Shared groups"],
  collections:["مجموعه‌ها","Collections"],observed_media:["رسانه‌های دیده‌شده در مرورگر","Media observed while browsing"],
  newest_first:["تازه‌ترین پیام‌ها اول","Newest messages first"],
  message_hint:["برای پیدا کردن پیام، بخشی از متنش را جست‌وجو کنید.","Search for a word or phrase to find a message."],
  close:["بستن","Close"],
  overview_intro:["گفت‌وگوها، پیام‌ها و وضعیت حسابت، یک‌جا.","Your chats, messages and account status in one place."],
  unread_chats:["گفت‌وگوهای خوانده‌نشده","Unread chats"],unread_messages:["پیام‌های خوانده‌نشده","Unread messages"],
  muted_chats:["بی‌صدا","Muted"],latest_activity:["آخرین فعالیت","Last activity"],by_type:["نوع گفت‌وگو","Chat type"],
  blocked_list:["حساب‌های مسدودشده","Blocked accounts"],unblock:["رفع مسدودی","Unblock"],
  open_cleanup:["رفتن به پاک‌سازی","Open cleanup"],
  activity_success:["انجام شد","Completed"],activity_failure:["ناموفق","Failed"],
  activity_unverified:["تأیید نشد","Unverified"],activity_login:["نشست تازه","New session"],
  cleanup:["پاک‌سازی حساب","Account cleanup"], queue:["صف انتخاب‌ها","Selected items"],
  run_cleanup:["اجرای صف","Run queue"], leave_action:["خروج","Leave"], block_action:["مسدودکردن","Block"],
  cleanup_hint:["موارد دلخواه را تیک بزنید. قبل از اجرا، اطلاعات و لینک‌های موجود ذخیره می‌شوند.",
    "Tick the items you want. Available details and links are backed up before changes."],
  private_link_warning:["ممکن است تلگرام پیوند بازگشت به بعضی گفت‌وگوهای خصوصی را ندهد.",
    "Telegram may withhold rejoin links for some private chats."],
  pending:["در صف","Queued"],working:["در حال بررسی","In progress"],left:["خارج شد","Left"],
  already_left:["از قبل عضو نبودید","Already left"], blocked:["مسدود شد","Blocked"],
  owner:["مالک باید ابتدا مالکیت را منتقل کند","Owner must transfer ownership first"],
  skipped:["اجرا نشد","Skipped"], unknown:["نتیجه تأیید نشد","Could not verify"],
  backup_phase:["در حال ذخیرهٔ پشتیبان","Saving backup"],
  cleanup_result:["گزارش پاک‌سازی","Cleanup report"],cleanup_backups:["پشتیبان‌های خروج","Cleanup backups"],
  cleanup_review:["بررسی پروفایل","Review profiles"],cleanup_compact:["فهرست فشرده","Compact list"],
  cleanup_profile:["نمایش پروفایل","Show profile"],cleanup_profile_hide:["بستن پروفایل","Hide profile"],
  cleanup_no_bio:["توضیحی در پروفایل ثبت نشده.","No bio on this profile."],
  cleanup_wait:["صف پس از پایان محدودیت تلگرام ادامه پیدا می‌کند.","The queue will resume after Telegram’s rate limit."],
  cleanup_report_tab:["گزارش و پشتیبان‌ها","Report and backups"],
  cleanup_requeue:["برگرداندن موارد اجرا‌نشده به صف","Requeue skipped items"],
  cleanup_refresh:["تازه‌کردن فهرست ناموفق بود. نتیجهٔ هر مورد در پایین آمده است.",
    "The list could not refresh. Individual results are shown below."],
};

const icons = {
  overview:"M3 3h7v8H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 15h7v6H3z",
  profile:"M20 21a8 8 0 0 0-16 0M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z",
  contacts:"M5 3h14v18H5zM3 8h4m-4 8h4m6-3a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm-4 4a4 4 0 0 1 8 0",
  chats:"M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l1.9-3A8.5 8.5 0 1 1 21 11.5zM8 12h8",
  channels:"M3 10v4h4l11 4V6L7 10zM7 14l2 6h3M21 9v6",
  groups:"M8 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7 7H2a6.5 6.5 0 0 1 13 0zm2-7a3 3 0 1 0 0-6m1 9a5 5 0 0 1 4 4",
  messages:"M4 4h16v13h-8l-5 4v-4H4zM8 9h8m-8 4h5",
  media:"M3 4h18v16H3zM8 9h.01M3 17l5-5 4 4 4-5 5 6",
  security:"M12 3l8 3v6c0 4-3 7-8 9-5-2-8-5-8-9V6zM9 12l2 2 4-4",
  analytics:"M3 21h18M6 17v-6m6 6V5m6 12V9",
  backups:"M3 5h18v4H3zM5 9v11h14V9m-10 4h6",
  automation:"M13 2 4 14h7l-1 8 10-12h-7z",
  settings:"M4 7h16M4 12h16M4 17h16M8 5v4m8 1v4m-6 1v4",
  activity:"M3 12h4l3-7 4 14 3-7h4",
  search:"M15.5 15.5 21 21M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0z",
  more:"M5 12h.01m7 0h.01m7 0h.01",sync:"M20 7v5h-5M4 17v-5h5m-4-3a8 8 0 0 1 12-4l3 3m-1 7a8 8 0 0 1-12 4l-3-3",
  arrow:"M9 5l7 7-7 7",file:"M6 3h8l4 4v14H6zM14 3v5h4",
  cleanup:"M3 6h18M9 6V3h6v3m4 0-1 15H6L5 6m5 4v7m4-7v7",
};
const areaLabels = {
  overview:["خانه","Home"],content:["محتوا","Content"],account:["حساب و امنیت","Account & Security"],
  tools:["ابزارها","Tools"],members:["اعضای سرویس","Service members"],cleanup:["مدیریت چت‌ها","Chat management"],
  scheduled:["زمان‌بندی‌شده","Scheduled"],filters:["فیلترها","Filters"],review:["صف عملیات","Operation queue"],
  report:["گزارش عملیات","Operation report"],
};
const areaIcons = {content:"file",account:"security",tools:"settings",members:"contacts",saved:"messages",
  drafts:"file",scheduled:"activity"};
const captions = {c:"channels",g:"groups",p:"private",b:"bots"};
const t = key => strings[key]?.[language === "en" ? 1 : 0] ?? key;
const areaLabel = key => areaLabels[key]?.[language === "en" ? 1 : 0] || t(key);
const num = input => input == null ? "—" : new Intl.NumberFormat(language).format(input);
const dates = input => input ? new Intl.DateTimeFormat(language,{dateStyle:"medium",timeStyle:"short"}).format(new Date(input)) : "";
const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (className) node.className = className;
  return node;
};
function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const node = document.createElementNS(ns,"svg");
  node.setAttribute("viewBox","0 0 24 24");
  node.setAttribute("aria-hidden","true");
  const path = document.createElementNS(ns,"path");
  path.setAttribute("d",icons[name] ?? icons.arrow);
  node.append(path);
  return node;
}
function btn(label, action, style, iconName) {
  const node = el("button",label,style);
  node.type = "button";
  if (iconName) node.prepend(icon(iconName));
  node.addEventListener("click",async () => {
    node.disabled = true;
    try { await action(); }
    catch (error) { notify(error.message || t("failed")); }
    finally { node.disabled = false; }
  });
  return node;
}
function notify(message) {
  clearTimeout(notificationTimer);
  toast.textContent = message;
  toast.hidden = false;
  notificationTimer = setTimeout(() => { toast.hidden = true; },4300);
}
async function api(path, {body, query, raw = false} = {}) {
  const url = new URL(proxy || path, location.href);
  if (proxy) url.searchParams.set("path",path);
  if (query) Object.entries(query).forEach(([key,value]) => {
    if (value !== "" && value != null) url.searchParams.set(key,value);
  });
  const headers = {"X-Telegram-Init-Data":launchData()};
  if (body) headers["Content-Type"] = "application/json";
  const response = await fetch(url,{method:body ? "POST" : "GET",headers,
    body:body ? JSON.stringify(body) : undefined,cache:"no-store",credentials:"omit"});
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const message = response.status === 403 ? t("open_bot") :
      error.wait ? `${t("failed")} ${num(error.wait)}s` : t("failed");
    throw Object.assign(new Error(message),{status:response.status});
  }
  return raw ? response.blob() : response.json();
}
const command = (action,target="",value="",extra="") =>
  api("api/command",{body:{action,target:String(target),value:String(value),extra:String(extra)}});
const dataList = (section, query) => api("api/browse",{body:{section,...query}});
function download(path,filename,query) {
  return api(path,{query,raw:true}).then(blob => {
    const url = URL.createObjectURL(blob);
    const link = el("a");
    link.href = url; link.download = filename; link.click();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  });
}
async function photo(path) {
  const payload = await api(path,{raw:true});
  const url = URL.createObjectURL(payload);
  const img = el("img",null,"profile-photo");
  img.alt = t("photo");
  img.onload = img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
  return img;
}
function heading(title, action) {
  const node = el("div",null,"heading");
  node.append(el("h1",title));
  if (action) node.append(action);
  return node;
}
function hero(title, description, iconName, status, actions = []) {
  const section = el("section",null,"hero");
  const copy = el("div",null,"hero-copy");
  if (status) copy.append(status);
  copy.append(el("h1",title),el("p",description,"hero-description"));
  if (actions.length) {
    const group = el("div",null,"hero-actions");
    group.append(...actions);
    copy.append(group);
  }
  const graphic = el("div",null,"hero-graphic");
  graphic.setAttribute("aria-hidden","true");
  const tile = el("span",null,"hero-glyph");
  tile.append(icon(iconName));
  graphic.append(tile);
  section.append(copy,graphic);
  return section;
}

function loadingScreen(section) {
  const status = el("div",null,"boot-loading");
  status.setAttribute("role","status");
  const cleanup = section === "cleanup";
  const iconName = cleanup ? "cleanup" : "overview";
  status.append(hero(t(section),t("loading"),iconName));
  const grid = el("div",null,"boot-grid");
  for (let index = 0; index < 4; index++) {
    const placeholder = el("span",null,"boot-placeholder");
    placeholder.setAttribute("aria-hidden","true");
    grid.append(placeholder);
  }
  status.append(grid);
  return status;
}
function panel(title,...items) {
  const box = el("section",null,"surface");
  if (title) box.append(el("h2",title));
  box.append(...items);
  return box;
}
function details(entries) {
  const list = el("dl",null,"details");
  for (const [key,value] of entries) {
    list.append(el("dt",t(key)),el("dd",value ?? "—"));
  }
  return list;
}
function choose(options,selected,change) {
  const node = el("select");
  for (const [value,label] of options) {
    const option = el("option",t(label));
    option.value = value; option.selected = value === selected;
    node.append(option);
  }
  node.addEventListener("change",() => change(node.value));
  return node;
}
function searchBox(current,submit) {
  const form = el("form",null,"tools");
  const input = el("input");
  input.type = "search"; input.value = current || ""; input.maxLength = 150;
  input.placeholder = t("search"); input.setAttribute("aria-label",t("search"));
  const button = el("button",t("search"));
  form.append(input,button);
  form.addEventListener("submit",event => { event.preventDefault(); submit(input.value.trim()); });
  return form;
}
function listRows(rows,itemIcon,open,{messages=false}={}) {
  const list = el("div",null,messages ? "list message-list" : "list");
  if (!rows.length) list.append(el("div",t("empty"),"empty"));
  for (const row of rows) {
    const button = btn("",() => open(row),"item",itemIcon);
    const label = el("span",null,"label");
    const title = el("strong",row.title || "—");
    title.dir = "auto";
    label.append(title);
    if (messages) {
      const preview = el("p",row.protected ? t("protected") : row.info || row.file || "—","message-preview");
      preview.dir = "auto";
      label.append(preview);
      const meta = [row.file, row.bytes && `${num(row.bytes)} B`, dates(row.date)].filter(Boolean);
      if (meta.length) label.append(el("small",meta.join(" · ")));
    } else if (row.info || row.date || row.bytes || row.file) {
      label.append(el("small",[row.info,row.file,row.bytes && `${num(row.bytes)} B`,dates(row.date)].filter(Boolean).join(" · ")));
    }
    button.append(label,icon("arrow"));
    list.append(button);
  }
  return list;
}
function pager(page,more,change) {
  const node = el("div",null,"pager");
  if (page > 0) node.append(btn(t("previous"),() => change(page - 1)));
  node.append(el("span",`${t("page")} ${num(page + 1)}`));
  if (more) node.append(btn(t("next"),() => change(page + 1)));
  return node;
}
function eventRows(rows) {
  const node = el("div",null,"list");
  if (!rows.length) node.append(el("p",t("empty"),"muted"));
  for (const [time,operation,outcome] of rows) {
    const item = el("div",null,"event");
    const types = {sync:"sync",backup:"backups",leave:"leave",login_detected:"activity_login",
      contact_save:"contacts",contact_delete:"contacts",profile_edit:"profile",
      session_revoke:"revoke",dialog_archive:"archive",dialog_pin:"pin",
      message_delete:"messages",scheduled_delete:"scheduled",draft_save:"drafts"};
    const outcomes = {ok:"activity_success",failed:"activity_failure",unverified:"activity_unverified",
      left:"left",already_left:"already_left",refresh_failed:"cleanup_refresh"};
    item.append(el("span",`${types[operation] ? t(types[operation]) : operation.replaceAll("_"," ")} · ${t(outcomes[outcome] || outcome)}`),
      el("small",dates(time)));
    node.append(item);
  }
  return node;
}
async function go(section,params={}) {
  clearTimeout(cleanupTimer);
  if (section === "content") section = "messages";
  if (section === "account") section = "profile";
  if (section === "tools") section = "cleanup";
  state = {...params,section};
  const version = ++revision;
  document.documentElement.lang = language;
  document.documentElement.dir = language === "en" ? "ltr" : "rtl";
  document.querySelector("#language").textContent = language === "en" ? "فا" : "EN";
  renderNavigation();
  content.replaceChildren(loadingScreen(section));
  if (!launchData()) {
    content.replaceChildren(hero("KILLER SELF",t("open_bot"),"overview"));
    return;
  }
  try {
    const view = await routes[section](state);
    if (version === revision) {
      const screen = el("div",null,"screen-enter");
      const tabs = areaTabs(section);
      if (tabs) screen.append(tabs);
      screen.append(...view);
      content.replaceChildren(screen);
      window.scrollTo({top:params.scrollTop || 0,behavior:"instant"});
    }
  } catch (error) {
    if (version === revision) {
      const tabs = areaTabs(section);
      content.replaceChildren(...(tabs ? [tabs] : []),heading(areaLabel(section)),
        panel(null,el("p",navigator.onLine === false ? (language === "en" ? "You're offline." : "اتصال اینترنت قطع است.")
          : error.message || t("failed")),btn(t("retry"),() => go(section,params))));
    }
  }
}
function currentLocation() {
  return {...state,scrollTop:window.scrollY};
}
function returnTo(location, fallback) {
  return location ? go(location.section,location) : go(fallback);
}
function tabsBar(entries,selected,select) {
  const tabs = el("div",null,"workspace-tabs");
  for (const [key,label] of entries) {
    const button = btn(label,() => select(key),"quiet");
    button.setAttribute("aria-pressed",String(key === selected));
    tabs.append(button);
  }
  return tabs;
}
function areaTabs(section) {
  if (section === "chat_detail" || section === "dialog_profiles" || (state.peer && state.returnLocation)) return null;
  const areas = {
    chats:["chats","contacts"],
    content:["messages","media","saved","drafts","scheduled"],
    account:["profile","security","blocked_list"],
    tools:["cleanup","analytics","backups","automation"],
    settings:isOwner ? ["settings","members"] : ["settings"],
  };
  const active = areaOf(section,state.from);
  const sections = areas[active];
  return sections?.length > 1 ? tabsBar(sections.map(key => [key,areaLabel(key)]),
    ["channels","groups"].includes(section) ? "chats" : section,key => go(key)) : null;
}
function renderNavigation() {
  const nav = document.querySelector("#navigation");
  const mobile = document.querySelector("#mobile-nav");
  const item = section => {
    const label = areaLabel(section);
    const button = btn(label,() => go(section),null,areaIcons[section] || section);
    button.title = label;
    if (section === areaOf(state.section,state.from)) button.setAttribute("aria-current","page");
    return button;
  };
  document.querySelector(".shell").classList.toggle("sidebar-compact",sidebarCompact);
  const collapse = btn(sidebarCompact ? "»" : "«",() => {
    sidebarCompact = !sidebarCompact;
    localStorage.setItem("killer-sidebar",sidebarCompact ? "compact" : "full");
    renderNavigation();
  },"sidebar-toggle");
  collapse.setAttribute("aria-label",language === "en" ? "Toggle sidebar" : "تغییر نمایش نوار کناری");
  const status = el("p",connected == null ? "" : t(connected ? "connected" : "disconnected"),"sidebar-status");
  const shortcuts = btn(t("search"),commandPalette,null,"search");
  shortcuts.title = `${t("search")} · Ctrl K`;
  nav.replaceChildren(collapse,shortcuts,...desktop.slice(0,5).map(item),
    el("span",language === "en" ? "System" : "سیستم","sidebar-group"),
    ...desktop.slice(5).map(item),status);
  const moreButton = btn(t("more"),openMore,null,"more");
  if (["account","settings","activity"].includes(areaOf(state.section))) moreButton.setAttribute("aria-current","page");
  mobile.replaceChildren(...mobileAreas.map(key => key === "more" ? moreButton : item(key)));
}
function showDialog(title, fields, submit, actionLabel=t("confirm")) {
  document.querySelector("#dialog-title").textContent = title;
  document.querySelector("#dialog-body").replaceChildren(...fields);
  const footer = document.querySelector("#dialog-footer");
  const apply = el("button",actionLabel,"primary");
  footer.replaceChildren(btn(t("cancel"),() => modal.close()),apply);
  modalForm.onsubmit = async event => {
    event.preventDefault();
    apply.disabled = true;
    try { await submit(); }
    catch (error) { notify(error.message || t("failed")); }
    finally { apply.disabled = false; }
  };
  if (!modal.open) modal.showModal();
}
function showMessage(title, fields) {
  showDialog(title,fields,() => modal.close(),t("close"));
  document.querySelector("#dialog-footer").firstChild.hidden = true;
}
function field(label,value="", multiline=false) {
  const wrapper = el("label",t(label),"field");
  const input = el(multiline ? "textarea" : "input");
  input.value = value; input.maxLength = multiline ? 4096 : 160;
  wrapper.append(input);
  return [wrapper,input];
}
async function confirmAction(action,label,target,value="",extra="") {
  const pending = await command(action,target,value,extra);
  showDialog(label,[el("p",pending.label,"surface")],async () => {
    const result = await command("confirm",pending.token);
    modal.close();
    if (!result.ok) throw new Error(t("failed"));
    notify(t("done"));
    if (action === "leave" || action === "contact_delete" || action === "revoke" || action === "message_delete") {
      await go(state.section);
    } else await go(state.section,state);
  });
}
function editOne(action,label,target,current="",multiline=false) {
  const [wrapper,input] = field(label,current,multiline);
  showDialog(t(label),[wrapper],async () => {
    if (action === "tag") {
      await command(action,target,input.value);
      modal.close();
      return go(state.section,state);
    }
    await confirmAction(action,t(label),target,input.value);
  });
}
function openMore() {
  const list = el("div",null,"list");
  for (const key of [...more,...(isOwner ? ["members"] : [])])
    list.append(btn(areaLabel(key),() => { modal.close(); return go(key); },"item",areaIcons[key] || key));
  showMessage(t("more"),[list]);
}
function commandPalette() {
  return go("search",{returnLocation:state.section === "search" ? state.returnLocation : currentLocation()});
}

async function overview() {
  const link = await api("api/link").catch(error => {
    if (error.status !== 404) throw error;
    return null;
  });
  isOwner = link?.state === "owner";
  if (link && !["owner","connected"].includes(link.state)) {
    connected = false;
    renderNavigation();
    return linkAccount(link);
  }
  const data = await api("api/overview");
  connected = data.connected;
  renderNavigation();
  if (!serverLanguageLoaded && data.connected) {
    serverLanguageLoaded = true;
    const preferences = await api("api/settings");
    if (["fa","en"].includes(preferences.language) && language !== preferences.language) {
      language = preferences.language;
      queueMicrotask(() => go("overview"));
    }
  }
  const status = data.syncing ? "syncing" : data.connected ? "connected" : "disconnected";
  const title = hero(areaLabel("overview"),t("overview_intro"),"chats",
    el("span",t(status),`status ${status}`),[
      btn(areaLabel("cleanup"),() => go("cleanup"),"primary","cleanup"),
      btn(t("sync"),async () => {
        notify(t("syncing")); await command("sync"); await go("overview");
      },"hero-secondary","sync"),
      ...(link?.state === "owner" ? [btn(language === "en" ? "Members" : "اعضای مینی‌اپ",
        () => go("members"),"hero-secondary","contacts")] : []),
    ]);
  const metrics = el("div",null,"metric-grid");
  for (const key of ["dialogs","contacts","pinned","archived"]) {
    const box = el("article",null,`metric metric-${key}`);
    const badge = el("span",null,"metric-icon");
    badge.append(icon({dialogs:"chats",unread_chats:"chats",unread_messages:"messages",
      pinned:"overview",archived:"backups"}[key] || key));
    box.append(badge,el("p",num(data[key]),"number"),el("p",t(key),"metric-label"));
    metrics.append(box);
  }
  const quick = el("div",null,"quick");
  for (const key of ["chats","contacts","security","backups"]) {
    quick.append(btn(t(key),() => go(key),null,key));
  }
  const grid = el("div",null,"overview-grid");
  grid.append(panel(t("quick"),quick),panel(t("recent"),eventRows(data.activity)));
  return [title,metrics,grid];
}
async function linkAccount(link) {
  const en = language === "en";
  const title = en ? "Connect your Telegram account" : "اتصال حساب تلگرام";
  const box = el("div",null,"actions");
  const current = revision;
  function loginForm(field,label,submitLabel,attributes) {
    const form = el("form");
    const input = el("input");
    Object.assign(input,attributes,{required:true,placeholder:label});
    input.setAttribute("aria-label",label);
    const submit = el("button",submitLabel,"button primary");
    submit.type = "submit";
    form.append(input,submit);
    form.addEventListener("submit",async event => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const value = input.value.trim().replace(/[۰-۹٠-٩]/g,digit => String(digit.charCodeAt(0) & 15));
        if (field === "code") input.value = "";
        const next = await api(`api/link/${field}`,{body:{[field]:value.replace(/\s/g,"")}});
        if (next.wait) notify(en ? `Try again in ${next.wait}s` : `${num(next.wait)} ثانیه دیگر امتحان کن`);
        else if (next.invalid) notify(en ? "Check the value and try again." : "مقدار واردشده را بررسی کن.");
        else await go("overview");
      } catch (error) { notify(error.message); }
      finally { submit.disabled = false; }
    });
    return form;
  }
  if (link.state === "waiting" || link.state === "restoring") {
    if (link.state === "waiting") {
      const blob = await api("api/link/qr",{raw:true}).catch(error => {
        if (error.status !== 404) throw error;
        return null;
      });
      if (blob) {
        const image = el("img");
        image.width = image.height = 220;
        image.alt = en ? "Telegram sign-in QR" : "کد QR ورود تلگرام";
        const url = URL.createObjectURL(blob);
        image.onload = image.onerror = () => URL.revokeObjectURL(url);
        image.src = url;
        image.style.background = "#fff";
        box.append(image,el("p",en ? "On another device, open Telegram → Settings → Devices → Link Desktop Device." :
          "در دستگاه دیگر، تلگرام را باز کن و از تنظیمات ← دستگاه‌ها ← اتصال دستگاه، این کد را اسکن کن."));
      }
    }
    const poll = async () => {
      if (current !== revision) return;
      try {
        const next = await api("api/link");
        if (current !== revision) return;
        if (next.state !== link.state) return go("overview");
        setTimeout(poll,2500);
      } catch (error) { notify(error.message); }
    };
    setTimeout(poll,2500);
  } else if (link.state === "code") {
    box.append(el("p",en ? "Enter the code sent by Telegram for this sign-in." :
      "کدی را وارد کن که تلگرام برای همین ورود فرستاده است."),
    loginForm("code",en ? "Login code" : "کد ورود",en ? "Verify code" : "تأیید کد",
      {inputMode:"numeric",autocomplete:"one-time-code",maxLength:8}));
  } else if (link.state === "password") {
    const form = el("form");
    const input = el("input");
    input.type = "password";
    input.required = true;
    input.maxLength = 256;
    input.placeholder = en ? "Telegram two-step password" : "رمز دومرحله‌ای تلگرام";
    const submit = el("button",en ? "Connect" : "اتصال","button primary");
    submit.type = "submit";
    form.append(input,submit);
    form.addEventListener("submit",async event => {
      event.preventDefault();
      submit.disabled = true;
      const password = input.value;
      input.value = "";
      try {
        const next = await api("api/link/password",{body:{password}});
        if (next.state !== "password") await go("overview");
        else notify(next.invalid ? (en ? "Incorrect password" : "رمز نادرست است") :
          (en ? "Wait before trying again" : "کمی صبر کن و دوباره امتحان کن"));
      } catch (error) { notify(error.message); }
      finally { submit.disabled = false; }
    });
    box.append(el("p",en ? "Your password is used to complete this sign-in and is not stored." :
      "رمز تنها برای تکمیل همین ورود به تلگرام استفاده می‌شود و ذخیره نمی‌شود."),form);
  } else {
    if (link.state === "wrong_account") box.append(el("p",en ? "Scan using the account that opened this Mini App." :
      "کد را با همان حسابی اسکن کن که مینی‌اپ را باز کرده."));
    box.append(el("p",en ? "Connect your account to manage it here. This service stores the Telegram session encrypted." :
      "حسابت را وصل کن تا همین‌جا مدیریتش کنی. نشست تلگرام به‌صورت رمزگذاری‌شده نگهداری می‌شود."));
    box.append(btn(en ? "Create sign-in QR" : "ساخت QR ورود",async () => {
      await api("api/link",{body:{}});
      await go("overview");
    },"primary"));
    box.append(loginForm("phone",en ? "+98… Phone number" : "شماره با پیش‌شمارهٔ کشور، مثل ‎+98",
      en ? "Send login code" : "ارسال کد ورود",{type:"tel",autocomplete:"tel",dir:"ltr",maxLength:24}));
  }
  return [heading(title),panel(null,box)];
}
async function membersScreen({page=0,query="",access="all"}) {
  const en = language === "en";
  const navigate = params => go("members",{query,access,...params});
  let data = await api("api/members",{query:{page,query,access}});
  if (!data.filters && (query || access !== "all")) {
    const matched = [];
    let index = 0;
    let batch;
    do {
      batch = index === page ? data : await api("api/members",{query:{page:index}});
      matched.push(...batch.members.filter(member => member.id.includes(query) &&
        (access === "all" || (member.state === "revoked") === (access === "revoked"))));
      index++;
    } while (batch.more && matched.length <= (page + 1) * 12);
    data = {members:matched.slice(page * 12,(page + 1) * 12),more:matched.length > (page + 1) * 12};
  }
  const rows = el("div",null,"list member-list");
  if (!data.members.length) rows.append(el("p",t("empty"),"muted"));
  for (const member of data.members) {
    const row = el("div",null,"item member-card");
    const label = el("div",null,"label");
    const captions = en ? {connected:"Connected",revoked:"Access revoked",waiting:"Awaiting QR",
      code:"Awaiting code",password:"Awaiting verification",restoring:"Reconnecting"} :
      {connected:"متصل",revoked:"دسترسی قطع شده",waiting:"در انتظار اسکن",code:"در انتظار کد",
        password:"در انتظار تأیید دومرحله‌ای",restoring:"در حال اتصال"};
    const revoked = member.state === "revoked";
    const caption = revoked && member.linked ? (en ? "Logout pending" : "لغو نشست تأیید نشده") :
      captions[member.state] || (member.linked ? (en ? "Session saved" : "نشست ذخیره شده") :
        (en ? "Disconnected" : "بدون اتصال"));
    const identity = el("div",null,"member-identity");
    if (member.photo) {
      const image = el("img");
      image.src = member.photo;
      image.alt = "";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error",() => image.remove());
      identity.append(image);
    }
    const name = el("strong",member.name || member.id);
    name.dir = "auto";
    identity.append(name);
    label.append(identity);
    if (member.name || member.username) {
      const meta = el("small",[member.username ? `@${member.username}` : "",member.id].filter(Boolean).join(" · "));
      meta.dir = "ltr";
      meta.style.textAlign = "start";
      label.append(meta);
    }
    label.append(el("small",
      `${en ? "Last activity" : "آخرین فعالیت"} · ${new Date(member.seen * 1000).toLocaleString(language)}`));
    const badge = el("span",caption,`member-state state-${member.state}`);
    row.append(label,badge);
    if (!revoked || member.linked !== false) row.append(btn(revoked ? (en ? "Retry logout" : "تلاش مجدد برای لغو نشست") :
      (en ? "Revoke access" : "قطع دسترسی"),() => {
      showDialog(en ? "Revoke member access?" : "دسترسی عضو قطع شود؟",[el("p",member.id)],async () => {
        const result = await api(`api/members/${member.id}/revoke`,{body:{}});
        modal.close();
        if (!result.telegram_logout) notify(en ? "Access disabled. Telegram logout could not be verified." :
          "دسترسی قطع شد. خروج از تلگرام تأیید نشد.");
        await navigate({page});
      });
    },"quiet"));
    rows.append(row);
  }
  const tools = el("div",null,"tools member-tools");
  const filters = el("select");
  filters.setAttribute("aria-label",en ? "Access status" : "وضعیت دسترسی");
  for (const [value,label] of [["all",t("all")],["active",en ? "Allowed" : "دارای دسترسی"],
    ["revoked",en ? "Revoked" : "قطع‌شده"]]) {
    const option = el("option",label);
    option.value = value;
    filters.append(option);
  }
  filters.value = access;
  filters.addEventListener("change",() => navigate({access:filters.value}));
  tools.append(filters,btn(t("refresh"),() => navigate({page}),"quiet","sync"));
  return [hero(en ? "Member sessions" : "نشست اعضا",
    en ? "Manage access to this Mini App." : "مدیریت دسترسی اعضا به مینی‌اپ.", "security"),
    searchBox(query,value => navigate({query:value.trim().replace(/[۰-۹٠-٩]/g,d => String(d.charCodeAt(0) & 15))
      .slice(0,80)})),tools,
    panel(null,rows,pager(page,data.more,value => navigate({page:value})))];
}
async function profile() {
  const data = await api("api/profile");
  const keys = ["first_name","last_name","username","about","id"];
  const actions = el("div",null,"actions");
  for (const key of keys.slice(0,4)) {
    actions.append(btn(`${t("edit")} ${t(key)}`,
      () => editOne("profile_edit",key,key,data[key],key === "about")));
  }
  if (data.photo) actions.append(btn(t("photo"),() => showProfilePhotos(0)));
  const box = panel(null,details([...keys.map(key => [key,data[key] || "—"]),
    ["Premium",data.premium ? t("enabled") : t("disabled")]]),actions);
  if (data.photo) {
    try { box.prepend(await photo("api/profile-photo")); } catch {}
  }
  return [heading(t("profile")),box];
}
async function showProfilePhotos(page) {
  const data = await api("api/profile-photos",{query:{page}});
  const grid = el("div",null,"quick");
  for (const [index,id] of data.items.entries()) {
    grid.append(btn(`${t("photo")} ${num(page*8+index+1)}`,async () => {
      const img = await photo(`api/profile-photos/${id}`);
      showDialog(t("photo"),[img,btn(t("back"),() => showProfilePhotos(page))],() => modal.close());
    }));
  }
  showDialog(t("photo"),[grid,pager(page,data.more,showProfilePhotos)],() => modal.close());
}
async function chats({section, page=0, query="", kind="all", privacy="all", sort="name", folder="",tag="",state=""}) {
  if (section === "channels") kind = "c";
  if (section === "groups") kind = "g";
  const filters = {query,kind,privacy,sort,folder,tag,state};
  const apply = object => go(section,{...filters,...object});
  const controls = searchBox(query,value => apply({query:value,page:0}));
  const dropdowns = el("div",null,"tools");
  const categories = [["all",t("all")],["p",language === "en" ? "Private" : "شخصی"],
    ["g",t("groups")],["c",t("channels")],["b",t("bots")]];
  const categoryTabs = tabsBar(categories,folder || tag ? "" : kind,
    value => go("chats",{kind:value,query,privacy,sort,state}));
  dropdowns.append(choose([["all","all"],["a","archived"],["favorites","favorites"],["tagged","tagged"]],
    ["a","favorites","tagged"].includes(kind) ? kind : "all",
    value => apply({kind:value,folder:"",tag:"",page:0})));
  dropdowns.append(choose([["all","all"],["public","public"],["private","private"]],privacy,
    value => apply({privacy:value,page:0})));
  if (!folder) {
    dropdowns.append(choose([["","all"],["unread","unread_chats"],["pinned","pinned"],["muted","muted_chats"]],
      state,value => apply({state:value,page:0})));
    dropdowns.append(choose([["name","name"],["latest","latest_activity"],["unread","unread_messages"],
      ["type","by_type"],["recent","recent_order"]],sort,value => apply({sort:value,page:0})));
  }
  if (section === "chats") {
    dropdowns.append(btn(t("folders"),async () => {
      const data = await dataList("folders");
      showDialog(t("folders"),[listRows(data.items,"chats",item => {
        modal.close(); return apply({folder:item.mode,page:0,privacy:"all",tag:""});
      })],() => modal.close());
    }));
    dropdowns.append(btn(t("collections"),async () => {
      const sets = await api("api/collections");
      showDialog(t("collections"),[listRows(sets.map(([title,count]) => ({title,info:num(count)})),"chats",
        item => { modal.close(); return apply({tag:item.title,folder:"",kind:"tagged",page:0}); })],
        () => modal.close());
    }));
  }
  const data = folder ? await dataList("folders",{mode:folder,query,page})
    : await dataList("chats",{kind,query,page,privacy,sort,tag,state});
  if (tag) dropdowns.append(btn(`#${tag} ×`,() => apply({tag:"",kind:"all",page:0})));
  const profileKind = ["b","g","c"].includes(kind) ? kind : "b";
  const advanced = el("details",null,"workspace-filter");
  advanced.open = Boolean(folder || tag || state || privacy !== "all" || sort !== "name" ||
    ["a","favorites","tagged"].includes(kind));
  advanced.append(el("summary",areaLabel("filters")),dropdowns);
  const actions = el("div",null,"tools");
  actions.append(btn(areaLabel("cleanup"),() => go("cleanup",{kind:profileKind}),"quiet","cleanup"),
    btn(t("dialog_profiles"),() => go("dialog_profiles",{kind:profileKind,query,returnLocation:currentLocation()}),"quiet","profile"));
  return [heading(t("chats"),actions),categoryTabs,controls,advanced,panel(null,listRows(data.items,"chats",
    item => go("chat_detail",{peer:item.id,from:section,returnLocation:currentLocation()})),
    pager(page,data.more,value => apply({page:value})))];
}
async function dialogProfiles({page=0,query="",kind="b",from="chats",returnPage=0,returnLocation}) {
  const data = await dataList("chats",{kind,page,query});
  const navigate = params => go("dialog_profiles",{kind,query,from,returnPage,returnLocation,...params});
  const filters = el("div",null,"tools");
  filters.append(choose([["b","bots"],["g","groups"],["c","channels"]],kind,
    value => navigate({kind:value})));
  const rows = el("div");
  if (!data.items.length) rows.append(listRows([],"chats"));
  for (const item of data.items) {
    const card = el("details",null,"bot-profile-card");
    const summary = el("summary");
    const avatar = el("span");
    avatar.append(cleanupAvatar(item));
    summary.append(avatar,el("strong",item.title));
    const body = el("div",null,"bot-profile-body");
    card.append(summary,body);
    async function load() {
      body.replaceChildren(el("p",t("loading"),"muted"));
      card.dataset.loaded = "1";
      try {
        const {info,image} = await cleanupProfile(item.id);
        const bio = el("p",info.about || t("cleanup_no_bio"),info.about ? "cleanup-bio" : "muted");
        bio.dir = "auto";
        body.replaceChildren(bio);
        if (info.username) {
          const username = el("bdi",`@${info.username}`,"muted");
          username.dir = "ltr";
          body.prepend(username);
        }
        const blob = image && await image;
        if (blob && card.isConnected) avatar.replaceChildren(cleanupAvatar(item,blob));
      } catch (error) {
        body.replaceChildren(el("p",error.message || t("failed"),"muted"),btn(t("retry"),load,"quiet"));
      }
    }
    card.addEventListener("toggle",() => {
      if (card.open && !card.dataset.loaded) void load();
    });
    card.open = kind === "b";
    rows.append(card);
  }
  return [heading(t("dialog_profiles")),btn(t("back"),() => returnLocation ?
    returnTo(returnLocation,from) : go(from,{kind,query,page:returnPage}),"quiet"),filters,
    searchBox(query,value => navigate({query:value})),
    panel(null,rows,pager(page,data.more,value => navigate({page:value})))];
}
async function chatDetail({peer,from="chats",returnLocation}) {
  const info = await api(`api/chat/${peer}`);
  const actions = el("div",null,"actions");
  const quick = el("div",null,"actions");
  const contentMode = mode => go("messages",{peer,mode,returnLocation:currentLocation()});
  quick.append(btn(t("history"),() => contentMode("")),
    btn(t("scheduled"),() => contentMode("scheduled")),
    btn(t("pinned"),() => contentMode("pinned")),
    btn(t("draft"),() => editOne("draft_save","draft",peer,"",true)));
  actions.append(
    btn(t(info.archived ? "unarchive" : "archive"),() => confirmAction("archive",
      t(info.archived ? "unarchive" : "archive"),peer,info.archived ? "0" : "1")),
    btn(t(info.pinned ? "unpin" : "pin"),() => confirmAction("pin",
      t(info.pinned ? "unpin" : "pin"),peer,info.pinned ? "0" : "1")),
    btn(t(info.favorite ? "unfavorite" : "favorite"),async () => {
      await command("favorite",peer,info.favorite ? "0" : "1"); await go("chat_detail",{peer,from,returnLocation});
    }),
    btn(t("tag"),() => editOne("tag","tag",peer,info.tag || "")));
  if (["c","g"].includes(info.kind) && Object.hasOwn(info,"auto_read")) {
    const en = language === "en";
    const title = en ? "Auto-read" : "خواندن خودکار";
    actions.append(btn(title,() => {
      const mode = el("select");
      const interval = el("select");
      mode.setAttribute("aria-label",title);
      interval.setAttribute("aria-label",en ? "Check interval" : "فاصلهٔ بررسی");
      for (const [value,label] of [["off",en ? "Off" : "خاموش"],["messages",en ? "Messages" : "پیام‌ها"],
        ["mentions",en ? "Mentions and reply badges" : "نشان منشن و ریپلای"],
        ["both",en ? "Messages and badges" : "پیام‌ها و نشان منشن و ریپلای"]]) {
        const option = el("option",label);
        option.value = value;
        mode.append(option);
      }
      for (const [value,label] of [[30,en ? "30 seconds" : "۳۰ ثانیه"],[60,en ? "1 minute" : "۱ دقیقه"],
        [300,en ? "5 minutes" : "۵ دقیقه"],[900,en ? "15 minutes" : "۱۵ دقیقه"]]) {
        const option = el("option",label);
        option.value = value;
        interval.append(option);
      }
      mode.value = info.auto_read?.mode || "off";
      interval.value = info.auto_read?.interval || "60";
      showDialog(title,[el("p",info.title),mode,interval],async () => {
        await command("auto_read",peer,mode.value,interval.value);
        modal.close();
        await go("chat_detail",{peer,from,returnLocation});
      },en ? "Save" : "ذخیره");
    },"quiet"));
  }
  if (["c","g","b"].includes(info.kind)) actions.append(btn(t("queue"),() => {
    selectCleanup({id:peer, title:info.title, kind:info.kind},true);
    return go("cleanup",{kind:info.kind});
  }));
  const box = panel(t("details"),details([["id",info.entity_id],["username",info.username ? `@${info.username}` : "—"],
    ["members",num(info.count)],["unread",num(info.unread)],["about",info.about],["tag",info.tag],
    ["link",info.invite || (info.username ? `https://t.me/${info.username}` : null)]]));
  if (info.photo) {
    try { box.prepend(await photo(`api/photo/${peer}`)); } catch {}
  }
  return [heading(info.title,btn(t("back"),() => returnTo(returnLocation,from))),box,
    panel(areaLabel("content"),quick),panel(areaLabel("tools"),actions)];
}
function contactForm(current) {
  const [first,firstInput] = field("first_name",current?.first_name || "");
  const [last,lastInput] = field("last_name",current?.last_name || "");
  const [username,userInput] = field("username");
  firstInput.required = true;
  userInput.required = !current;
  showDialog(t(current ? "edit" : "add"),current ? [first,last] : [username,first,last],() =>
    confirmAction(current ? "contact_edit" : "contact_add",t(current ? "edit" : "add"),
      current?.id || userInput.value.trim(),firstInput.value.trim(),lastInput.value.trim()));
}
async function contacts({page=0,query=""}) {
  const data = await dataList("contacts",{page,query});
  const actions = el("div",null,"actions");
  actions.append(btn(t("add"),() => contactForm(null),"primary"),btn(t("sync"),async () => {
    await command("contacts_sync"); await go("contacts");
  }));
  return [heading(t("contacts"),actions),searchBox(query,value => go("contacts",{query:value})),
    panel(null,listRows(data.items,"profile",async item => {
      const user = await api(`api/contact/${item.id}`);
      const controls = el("div",null,"actions");
      controls.append(btn(t("edit"),() => contactForm(user)),btn(t("delete"),
        () => confirmAction("contact_delete",t("delete"),user.id),"danger"));
      controls.append(btn(t("shared_groups"),async () => {
        const groups = await api(`api/contact/${item.id}/groups`);
        showDialog(t("shared_groups"),groups.length ? groups.map(group => el("p",group)) :
          [el("p",t("empty"))],() => modal.close());
      }));
      showDialog(item.title,[details([["username",user.username],["phone",user.phone],["id",user.id]]),controls],
        () => modal.close());
    }),pager(page,data.more,value => go("contacts",{query,page:value})))];
}
async function messages({section,page=0,query="",peer="",mode="",list="messages",after="",before="",sender="",returnLocation,layout="grid"}) {
  if (section === "saved") peer = "me";
  if (section === "drafts") list = "drafts";
  if (section === "scheduled") {
    if (!peer) {
      const data = await dataList("chats",{page,query});
      return [heading(areaLabel("scheduled")),searchBox(query,value => go("scheduled",{query:value})),
        panel(null,listRows(data.items,"chats",item => go("scheduled",{peer:item.id,
          returnLocation:currentLocation()})),pager(page,data.more,value => go("scheduled",{page:value,query})))];
    }
    mode = "scheduled";
  }
  const filters = {query,peer,mode,list,after,before,sender,returnLocation,layout};
  const apply = changes => go(section,{...filters,...changes});
  const tools = el("div",null,"tools");
  if (section === "media") tools.append(choose([["photo","photo"],["video","video"],["file","file"],["audio","audio"],["voice","voice"]],
    mode || "photo",value => apply({mode:value,page:0})));
  if (section === "media") tools.append(btn(layout === "grid" ?
    (language === "en" ? "List view" : "نمای فهرست") : (language === "en" ? "Grid view" : "نمای شبکه‌ای"),
    () => apply({page,layout:layout === "grid" ? "list" : "grid"}),"quiet"));
  if (["media","messages"].includes(section) && !returnLocation && list !== "drafts") {
    tools.append(btn(t("chats"),async () => {
      const results = el("div",null,"list");
      let pickerVersion = 0;
      const paint = async (pickerQuery="",pickerPage=0) => {
        const version = ++pickerVersion;
        const data = await dataList("chats",{query:pickerQuery,page:pickerPage});
        if (version !== pickerVersion) return;
        results.replaceChildren(listRows(data.items,"chats",item => {
          modal.close();
          return apply({peer:item.id,page:0});
        }),pager(pickerPage,data.more,next => paint(pickerQuery,next)));
      };
      showMessage(t("chats"),[searchBox("",value => paint(value)),results]);
      await paint();
    },"quiet"));
    if (peer) tools.append(btn(`${t("all")} ×`,() => apply({peer:"",page:0}),"quiet"));
  }
  let result = {items:[],more:false};
  if (section === "media") result = await dataList("media",{page,query,mode:mode || "photo",after,before,sender,peer});
  else if (list === "drafts") result = await dataList("drafts",{page});
  else if (peer || query || sender) result = await dataList("messages",{page,query,peer,mode,after,before,sender});
  const open = async item => {
    if (list === "drafts") return editOne("draft_save","draft",item.id,item.info,true);
    const message = await api(`api/message/${item.id}`);
    const operations = el("div",null,"actions");
    if (message.has_media) operations.append(btn(t("download"),
      () => download(`api/media/${item.id}`,message.file || "telegram-media")));
    if (message.deletable) operations.append(btn(t("delete"),
      () => confirmAction("message_delete",t("delete"),item.id),"danger"));
    const body = el("p",message.protected ? t("protected") : message.info || "—","message-body");
    body.dir = "auto";
    const meta = [dates(message.date),message.sender,message.file,message.mime,
      message.bytes && `${num(message.bytes)} B`].filter(Boolean);
    const preview = el("div",null,"media-preview");
    const mime = message.mime || (section === "media" && (mode || "photo") === "photo" ? "image/jpeg" : "");
    const mediaTag = /^image\/(jpeg|png|gif|webp)$/.test(mime) ? "img" :
      /^video\/(mp4|webm)$/.test(mime) ? "video" : /^audio\/(mpeg|ogg|mp4|wav)$/.test(mime) ? "audio" : "";
    if (message.has_media && mediaTag) operations.prepend(btn(t("preview"),async () => {
      const blob = await api(`api/media/${item.id}`,{raw:true});
      if (!preview.isConnected || !modal.open) return;
      if (mediaPreviewUrl) URL.revokeObjectURL(mediaPreviewUrl);
      mediaPreviewUrl = URL.createObjectURL(new Blob([blob],{type:mime}));
      const player = el(mediaTag);
      if (mediaTag === "img") player.alt = message.file || t("photo");
      else player.controls = true;
      player.src = mediaPreviewUrl;
      preview.replaceChildren(player);
    },"quiet"));
    showMessage(message.title,[el("p",meta.join(" · "),"message-meta muted"),body,preview,operations]);
  };
  const idle = !peer && !query && !sender && section === "messages" && list !== "drafts";
  const items = idle ? el("p",t("message_hint"),"muted") :
    listRows(result.items,section,open,{messages:list !== "drafts"});
  if (section === "media" && layout === "grid" && result.items.length) items.classList.add("media-grid");
  const search = list === "drafts" || mode === "scheduled" ? el("span")
    : searchBox(query,value => apply({query:value,page:0}));
  if (list !== "drafts" && mode !== "scheduled") {
    tools.append(btn(t("search") + " · " + t("details"),() => {
      const [lower,start] = field("after",after); start.type = "date";
      const [upper,end] = field("before",before); end.type = "date";
      const [senderLabel,person] = field("sender",sender);
      showDialog(t("search"),[lower,upper,senderLabel],async () => {
        modal.close(); await apply({after:start.value,before:end.value,sender:person.value.trim(),page:0});
      });
    }));
  }
  const caption = result.items.length && list !== "drafts" && mode !== "scheduled"
    ? t("newest_first") : null;
  return [heading(areaLabel(section),returnLocation ? btn(t("back"),() => returnTo(returnLocation,"messages")) : null),
    tools,search,panel(caption,items,
    pager(page,result.more,value => apply({page:value})))];
}
async function security({page=0}) {
  const [security,data] = await Promise.all([api("api/security"),dataList("sessions",{page})]);
  const privacy = el("div",null,"actions");
  for (const key of security.privacy) privacy.append(btn(t(key),async () => {
    const rules = await api(`api/privacy/${key}`);
    showDialog(t(key),rules.map(([kind,count]) => el("p",`${t(kind)}${count ? ` · ${num(count)}` : ""}`)),
      () => modal.close());
  }));
  return [heading(t("security")),
    panel(t("two_factor"),el("p",t(security.two_factor ? "enabled" : "disabled"))),
    panel(t("devices"),listRows(data.items,"security",item => {
      const action = item.current ? el("p",t("current")) : btn(t("revoke"),
        () => confirmAction("revoke",t("revoke"),item.id),"danger");
      showDialog(item.title,[el("p",item.info),el("p",dates(item.date),"muted"),action],() => modal.close());
    }),pager(page,data.more,value => go("security",{page:value}))),panel(t("privacy"),privacy)];
}
async function blockedList({page=0}) {
  const data = await dataList("blocked",{page});
  return [heading(t("blocked_list")),
    panel(null,listRows(data.items,"security",item => confirmAction("unblock",t("unblock"),item.id)),
      pager(page,data.more,value => go("blocked_list",{page:value})))];
}
async function analytics() {
  const data = await api("api/analytics");
  const summary = el("div");
  const total = Object.values(data.kinds).reduce((a,b) => a + b,0);
  for (const [kind,count] of Object.entries(data.kinds)) {
    const label = el("div",null,"bar-label"); label.append(el("span",t(captions[kind])),el("strong",num(count)));
    const bar = el("div",null,"bar"); const fill = el("i"); fill.style.width = `${total ? count / total * 100 : 0}%`;
    bar.append(fill); summary.append(label,bar);
  }
  const ns = "http://www.w3.org/2000/svg";
  const chart = document.createElementNS(ns,"svg");
  chart.setAttribute("viewBox","0 0 420 120"); chart.setAttribute("class","trend");
  chart.setAttribute("role","img"); chart.setAttribute("aria-label",t("trends"));
  const values = data.history.map(item => item[1]);
  if (values.length > 1) {
    const low = Math.min(...values)-1, span = Math.max(...values)-low;
    const polyline = document.createElementNS(ns,"polyline");
    polyline.setAttribute("points",values.map((value,index) =>
      `${10 + index*400/(values.length-1)},${110 - (value-low)*96/span}`).join(" "));
    chart.append(polyline);
  }
  const exports = el("div",null,"actions");
  for (const type of ["json","csv"]) exports.append(btn(t(`export_${type}`),() =>
    download(`api/export/${type}`,`killer-statistics.${type}`)));
  return [heading(t("analytics")),el("p",t("data_source"),"muted"),
    panel(t("distribution"),summary,details([["archived",num(data.archived)],["storage",`${num(data.database_bytes)} B`]])),
    panel(t("observed_media"),data.observed_media.length ? details(data.observed_media.map(
      ([kind,count,bytes]) => [kind,`${num(count)} · ${num(bytes)} B`])) : el("p",t("empty"),"muted")),
    panel(t("trends"),values.length > 1 ? chart : el("p",t("empty"),"muted"),exports)];
}
async function backups({page=0}) {
  const data = await dataList("backups",{page});
  const create = btn(t("create_backup"),async () => {
    await command("backup"); notify(t("done")); await go("backups");
  },"primary","backups");
  return [heading(t("backups"),create),panel(null,el("p",t("app_backup"),"muted"),
    listRows(data.items.map(item => ({...item,info:item.bytes == null ? "" : `${num(item.bytes)} B`})),"file",async item => {
      const data = await api(`api/backup/${item.id}`);
      showDialog(t("preview"),[details([["schema",data.schema],["dialogs",num(data.chats)]]),
        btn(t("download"),() => download(`api/backup/${item.id}`,item.id,{export:true}))],() => modal.close());
    }),pager(page,data.more,value => go("backups",{page:value})))];
}
async function activity({page=0}) {
  const data = await dataList("activity",{page});
  return [heading(t("activity")),panel(null,eventRows(data.items.map(item => [item.date,item.title,item.info])),
    pager(page,data.more,value => go("activity",{page:value})))];
}
async function settings({section}) {
  const data = await api("api/settings");
  const controls = el("div",null,"list");
  const keys = section === "automation" ? ["sync_enabled","automatic_backup","summary","inactivity_report"] : ["login_alerts"];
  for (const key of keys) {
    const option = el("label",t(key),"event");
    option.append(choose([["on","enabled"],["off","disabled"]],data[key],async value => {
      try { await command("preference",key,value); notify(t("done")); }
      catch (error) { notify(error.message); await go(section); }
    }));
    controls.append(option);
  }
  if (section === "settings") {
    const row = el("label",t("backup_keep"),"event");
    const input = el("input"); input.type = "number"; input.min = 1; input.max = 100; input.value = data.backup_keep;
    row.append(input,btn(t("confirm"),async () => {
      if (!input.reportValidity()) return;
      await command("preference","backup_keep",input.value); notify(t("done"));
    }));
    controls.append(row);
    const plugins = await api("api/plugins");
    for(const plugin of plugins) {
      const description = el("label",`${t(plugin.id)} · ${plugin.version}`,"event");
      description.append(choose([["on","enabled"],["off","disabled"]],plugin.enabled ? "on" : "off",async value => {
        await command("preference",`plugin:${plugin.id}`,value); await go("settings");
      }));
      controls.append(description);
      if (plugin.enabled && plugin.id === "inactivity") controls.append(btn(t("inactivity"),async () => {
        const rows = await api("api/inactivity");
        showDialog(t("inactivity"),rows.length ? rows.map(([title,date]) => el("p",`${title} · ${dates(date)}`)) :
          [el("p",t("empty"))],()=>modal.close());
      }));
    }
  }
  return [heading(t(section)),panel(null,controls)];
}
async function unifiedSearch({query="",source="chats",page=0,mode="file",returnLocation}) {
  const controls = el("div",null,"tools");
  const windowState = {query,source,mode,returnLocation};
  controls.append(choose([["chats","chats"],["contacts","contacts"],["messages","messages"],
    ["saved","saved"],["media","media"]],source,value => go("search",{...windowState,source:value})));
  if (source === "media") controls.append(choose([["file","file"],["photo","photo"],["video","video"],
    ["audio","audio"],["voice","voice"]],mode,value => go("search",{...windowState,mode:value})));
  const output = [heading(t("global_search"),btn(t("back"),() => returnTo(returnLocation,"overview"))),
    searchBox(query,value => go("search",{...windowState,query:value})),controls];
  if (query) {
    const section = source === "saved" ? "messages" : source;
    const data = await dataList(section,{query,page,peer:source === "saved" ? "me" : "",mode:source === "media" ? mode : ""});
    const open = item => source === "chats" ? go("chat_detail",{peer:item.id,from:"search",returnLocation:currentLocation()}) :
      source === "contacts" ? go("contacts",{query:item.title}) :
      api(`api/message/${item.id}`).then(message => showDialog(message.title,
        [el("p",message.protected ? t("protected") : message.info || "—")],() => modal.close()));
    output.push(panel(null,el("p",t(["chats","contacts"].includes(source) ? "data_source" : "live"),"muted"),
      listRows(data.items,source,open),pager(page,data.more,value => go("search",{...windowState,page:value}))));
  }
  const recent = await api("api/search-history");
  if (recent.length) {
    const buttons = el("div",null,"actions");
    for (const word of recent.slice(0,10)) buttons.append(btn(word,() => go("search",{...windowState,query:word})));
    buttons.append(btn(t("clear_search"),() => confirmAction("search_clear",t("clear_search"),""),"danger"));
    output.push(panel(t("search_history"),buttons));
  }
  return output;
}
function selectCleanup(item, checked) {
  if (!checked) return cleanupSelection.delete(item.id);
  cleanupSelection.set(item.id,item);
  return true;
}
async function submitCleanup(ids) {
  const value = ids.join(",");
  if (value.length <= 4000) return command("cleanup_start","",value);
  let token = "";
  let chunk = "";
  for (const id of ids) {
    if (chunk.length + id.length + 1 > 4000) {
      ({token} = await command("cleanup_stage",token,chunk));
      chunk = "";
    }
    chunk += chunk ? `,${id}` : id;
  }
  if (chunk) ({token} = await command("cleanup_stage",token,chunk));
  return command("cleanup_commit",token);
}
function cleanupProfile(id) {
  if (cleanupProfiles.has(id)) return cleanupProfiles.get(id);
  if (cleanupProfiles.size >= 32) cleanupProfiles.delete(cleanupProfiles.keys().next().value);
  const request = api(`api/chat/${id}`).then(info => ({
    info,
    image: info.photo ? api(`api/photo/${id}`,{raw:true}).catch(() => null) : null,
  })).catch(error => {
    if (cleanupProfiles.get(id) === request) cleanupProfiles.delete(id);
    throw error;
  });
  cleanupProfiles.set(id,request);
  return request;
}
function cleanupAvatar(item,blob) {
  const avatar = el("span",null,"cleanup-avatar");
  if (!blob) {
    avatar.textContent = [...item.title.trim()][0] || "—";
    avatar.setAttribute("aria-hidden","true");
    return avatar;
  }
  const img = el("img");
  img.alt = t("photo");
  const url = URL.createObjectURL(blob);
  img.onload = img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
  avatar.append(img);
  return avatar;
}
function cleanupRows(items, changed, disabled, kind) {
  const rows = el("div",null,"cleanup-list");
  if (!items.length) rows.append(el("p",t("empty"),"muted"));
  for (const item of items) {
    const card = el("article",null,"cleanup-card");
    const row = el("div",null,"cleanup-row");
    const label = el("label",null,"cleanup-target");
    const checkbox = el("input");
    checkbox.type = "checkbox";
    checkbox.checked = cleanupSelection.has(item.id);
    checkbox.disabled = disabled;
    checkbox.addEventListener("change",() => {
      if (!selectCleanup(item,checkbox.checked)) checkbox.checked = false;
      changed();
    });
    const title = el("span",item.title);
    title.dir = "auto";
    label.append(checkbox,title);
    row.append(label,el("small",item.kind === "b" ? t("block_action") : item.info ? t("public") : t("private")));
    card.append(row);
    if (cleanupView === "review") {
      const body = el("div",null,"cleanup-profile");
      body.id = `cleanup-profile-${item.id}`;
      const toggle = btn("",refreshProfile,"quiet profile-toggle","profile");
      toggle.setAttribute("aria-controls",body.id);
      row.append(toggle);
      card.append(body);
      const isOpen = () => expandedProfiles.get(item.id) ?? (kind === "b");
      function updateToggle() {
        const open = isOpen();
        const caption = t(open ? "cleanup_profile_hide" : "cleanup_profile");
        toggle.setAttribute("aria-expanded",String(open));
        toggle.setAttribute("aria-label",`${caption} · ${item.title}`);
        toggle.title = caption;
        body.hidden = !open;
      }
      async function paintProfile() {
        if (body.dataset.loaded === "1" || body.dataset.loading === "1") return;
        body.dataset.loading = "1";
        body.replaceChildren(cleanupAvatar(item),el("p",t("loading"),"muted"));
        try {
          const {info,image} = await cleanupProfile(item.id);
          const meta = el("small",[info.username ? `@${info.username}` : "",
            info.count != null ? `${num(info.count)} ${t("members")}` : ""].filter(Boolean).join(" · "),"muted");
          const bio = el("p",info.about || t("cleanup_no_bio"),info.about ? "cleanup-bio" : "muted");
          bio.dir = "auto";
          const text = el("div",null,"cleanup-profile-text");
          if (meta.textContent) text.append(meta);
          text.append(bio);
          const avatar = cleanupAvatar(item);
          const avatarSlot = el("div");
          avatarSlot.append(avatar);
          body.replaceChildren(avatarSlot,text);
          body.dataset.loaded = "1";
          if (image) {
            const blob = await image;
            if (blob) avatarSlot.replaceChildren(cleanupAvatar(item,blob));
          }
        } catch (error) {
          body.replaceChildren(el("p",error.message || t("failed"),"muted"),
            btn(t("retry"),paintProfile,"quiet"));
        } finally {
          delete body.dataset.loading;
        }
      }
      function refreshProfile() {
        expandedProfiles.set(item.id,!isOpen());
        updateToggle();
        if (!body.hidden) void paintProfile();
      }
      updateToggle();
      if (!body.hidden) void paintProfile();
    }
    rows.append(card);
  }
  return rows;
}
async function openCleanupBackup(name) {
  const data = await api(`api/cleanup/${name}`);
  const rows = data.items.map(item => {
    const row = el("article",null,"surface");
    row.append(el("strong",item.title),el("p",[`ID ${item.entity_id}`,
      item.members != null ? `${t("members")} ${num(item.members)}` : ""].filter(Boolean).join(" · "),"muted"));
    if (item.about) row.append(el("p",item.about));
    for (const url of [...new Set([item.public_url,item.invite].filter(Boolean))]) {
      const line = el("p",null,"backup-link");
      if (/^https:\/\/(t\.me|telegram\.me)\//.test(url)) {
        const anchor = el("a",url);
        anchor.href = url;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        line.append(anchor);
      } else line.textContent = url;
      row.append(line);
    }
    return row;
  });
  showMessage(t("cleanup_backups"),rows);
}
async function cleanup({kind="c",page=0,query="",stage="browse"}) {
  const navigate = changes => go("cleanup",{kind,page,query,...changes});
  const sections = tabsBar([["browse",areaLabel("cleanup")],
    ["review",`${areaLabel("review")} · ${num(cleanupSelection.size)}`],["report",areaLabel("report")]],
    stage,value => navigate({stage:value}));
  const [data,status] = await Promise.all([
    stage === "browse" ? dataList("chats",{kind,page,query}) : null,api("api/cleanup"),
  ]);
  const job = status.job;
  const running = job && ["backup","running"].includes(job.phase);
  const queue = el("div",null,"cleanup-queue");
  const renderQueue = () => {
    const count = cleanupSelection.size;
    const list = el("div",null,"cleanup-list");
    for (const item of cleanupSelection.values()) {
      const row = el("div",null,"event");
      const action = item.kind === "b" ? "block_action" : "leave_action";
      row.append(el("span",item.title),el("small",t(action)),btn("×",() => {
        cleanupSelection.delete(item.id);
        return navigate({stage:"review"});
      }));
      list.append(row);
    }
    const footer = el("div",null,"cleanup-footer");
    const run = btn(t("run_cleanup"),() => {
      const ids = [...cleanupSelection.keys()];
      if (!ids.length || running) return;
      showDialog(t("run_cleanup"),[el("p",`${num(ids.length)} · ${areaLabel("review")}`),
        el("p",t("private_link_warning"),"muted")],async () => {
        await submitCleanup(ids);
        for (const id of ids) cleanupSelection.delete(id);
        modal.close();
        await navigate({stage:"report"});
      },t("run_cleanup"));
    },"danger");
    run.disabled = !count || Boolean(running);
    footer.append(el("strong",`${t("queue")} · ${num(count)}`),run);
    queue.replaceChildren(footer,...(count ? [list,el("p",t("private_link_warning"),"muted")] : []));
  };
  if (stage === "review") {
    renderQueue();
    return [heading(areaLabel("review")),sections,queue];
  }
  const filters = el("div",null,"tools");
  filters.append(choose([["c","channels"],["g","groups"],["b","bots"]],kind,
    value => go("cleanup",{kind:value,query:"",page:0})));
  const modes = el("div",null,"cleanup-modes");
  for (const mode of ["review","compact"]) {
    const option = btn(t(`cleanup_${mode}`),() => {
      if (cleanupView === mode) return;
      cleanupView = mode;
      localStorage.setItem("killer-cleanup-view",mode);
      return go("cleanup",{kind,page,query});
    },"quiet");
    option.setAttribute("aria-pressed",String(cleanupView === mode));
    modes.append(option);
  }
  filters.append(modes);
  const report = el("details",null,"cleanup-report");
  const reportTitle = el("summary");
  const reportBody = el("div",null,"cleanup-report-body");
  report.open = stage === "report" || cleanupReportOpen;
  report.append(reportTitle,reportBody);
  let reportStatus = status;
  function paintReport() {
    const {job,backups} = reportStatus;
    const complete = job?.items.filter(item => !["pending","working"].includes(item.status)).length;
    reportTitle.textContent = job ?
      `${t("cleanup_report_tab")} · ${num(complete)} / ${num(job.items.length)}` :
      `${t("cleanup_report_tab")}${backups.length ? ` · ${num(backups.length)}` : ""}`;
    if (!report.open) {
      reportBody.replaceChildren();
      return;
    }
    const result = [];
    const scroll = reportBody.querySelector(".cleanup-results")?.scrollTop || 0;
    if (job) {
      const list = el("div",null,"list cleanup-results");
      for (const item of job.items) {
        const row = el("div",null,"event");
        row.append(el("span",item.title),el("small",t(item.status)));
        list.append(row);
      }
      const label = job.wait ? t("cleanup_wait") :
        job.phase === "backup" ? t("backup_phase") : job.phase === "running" ?
        t("working") : job.phase === "failed" ? t("failed") : t("done");
      const elements = [el("p",job.wait ? `${label} · ${num(job.wait)}s` : label,"muted")];
      if (job.refresh_failed) elements.push(el("p",t("cleanup_refresh"),"muted"));
      elements.push(list);
      if (job.backup) elements.push(btn(t("preview"),() => openCleanupBackup(job.backup)));
      if (!running && job.items.some(item => item.status === "skipped")) {
        elements.push(btn(t("cleanup_requeue"),() => {
          for (const item of job.items.filter(item => item.status === "skipped")) selectCleanup(item,true);
          return go("cleanup",{kind,page,query});
        }));
      }
      result.push(panel(t("cleanup_result"),...elements));
    }
    if (backups.length) {
      result.push(panel(t("cleanup_backups"),...backups.slice(0,15).map((name,index) =>
        btn(`${t("preview")} ${num(index + 1)} · ${name.slice(0,8)}`,() => openCleanupBackup(name)))));
    }
    if (!result.length) result.push(el("p",t("empty"),"muted"));
    reportBody.replaceChildren(...result);
    const list = reportBody.querySelector(".cleanup-results");
    if (list) list.scrollTop = scroll;
  }
  report.addEventListener("toggle",() => {
    if (!report.isConnected) return;
    cleanupReportOpen = report.open;
    paintReport();
  });
  paintReport();
  if (running) {
    const current = revision;
    cleanupTimer = setTimeout(async function refresh() {
      if (revision !== current) return;
      try {
        const update = await api("api/cleanup");
        if (revision !== current) return;
        if (!update.job || update.job.id !== job.id || !["backup","running"].includes(update.job.phase)) {
          await navigate({stage});
          return;
        }
        reportStatus = update;
        paintReport();
      } catch (error) {
        notify(error.message);
      }
      if (revision === current) cleanupTimer = setTimeout(refresh,4000);
    },4000);
  }
  filters.append(btn(t("dialog_profiles"),() => go("dialog_profiles",{
    kind,query,page,from:"cleanup",returnPage:page,
  }),"accent","profile"));
  if (stage === "report") return [heading(areaLabel("report")),sections,report];
  return [heading(areaLabel("cleanup")),sections,
    el("p",t("cleanup_hint"),"muted"),
    filters,searchBox(query,value => go("cleanup",{kind,query:value,page:0})),
    panel(null,cleanupRows(data.items,() => {
      sections.children[1].textContent = `${areaLabel("review")} · ${num(cleanupSelection.size)}`;
    },running,kind),
      pager(page,data.more,value => go("cleanup",{kind,query,page:value})))];
}
const routes = {overview,members:membersScreen,profile,chats,channels:chats,groups:chats,dialog_profiles:dialogProfiles,chat_detail:chatDetail,
  contacts,messages,media:messages,saved:messages,drafts:messages,scheduled:messages,security,analytics,backups,activity,automation:settings,settings,
  search:unifiedSearch,cleanup,blocked_list:blockedList};

document.querySelector("#command").replaceChildren(icon("search"));
modal.addEventListener("close",() => {
  if (mediaPreviewUrl) URL.revokeObjectURL(mediaPreviewUrl);
  mediaPreviewUrl = null;
});
document.querySelector("#command").addEventListener("click",commandPalette);
document.querySelector("#language").addEventListener("click",async () => {
  language = language === "fa" ? "en" : "fa";
  localStorage.setItem("killer-language",language);
  serverLanguageLoaded = true;
  if (launchData()) {
    try { await command("preference","language",language); }
    catch (error) { notify(error.message); }
  }
  await go(state.section,state);
});
document.querySelector(".brand").addEventListener("click",event => { event.preventDefault(); go("overview"); });
document.addEventListener("keydown",event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault(); commandPalette();
  }
});
telegram?.ready();
telegram?.expand();
if (telegram?.isVersionAtLeast?.("6.9")) telegram.setHeaderColor?.("#030407");
if (telegram?.isVersionAtLeast?.("6.1")) telegram.setBackgroundColor?.("#030407");
go(new URLSearchParams(location.search).get("view") === "cleanup" ? "cleanup" : "overview");
