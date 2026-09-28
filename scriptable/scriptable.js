// Paste this entire file into a Scriptable script named CEITI.
const CONFIG = {
  serverUrl: "https://ceiti-scriptable.onrender.com",
  group: "P-2434R",
  subgroup: 1,
  lessonNotificationMinutes: 10,
  endOfDayNotificationMinutes: 15,
  tomorrowSummaryHour: 19,
  tomorrowSummaryMinute: 40,
};

const PREFIX = "ceiti_";

function buildNotifications(plan, settings, now = new Date()) {
  if (!plan || plan.timezone !== "Europe/Chisinau" || !Array.isArray(plan.days) || plan.days.length !== 2)
    throw new Error("Invalid schedule response");
  const result = [];
  const add = (id, title, body, instant) => {
    const date = new Date(instant);
    if (!Number.isFinite(date.getTime())) throw new Error("Invalid notification time");
    if (date > now) result.push({ id: PREFIX + id, title, body, date });
  };
  for (const day of plan.days) {
    if (day.group !== settings.group || day.subgroup !== settings.subgroup || !Array.isArray(day.lessons))
      throw new Error("Wrong group or invalid lessons");
    if (!day.complete) { console.warn("Unconfirmed week: " + day.date); continue; }
    if (day.stale) console.warn("Cached schedule: " + day.fetched_at);
    // Also prepare tomorrow's lessons, so missing the morning automation is less harmful.
    const slots = new Map();
    for (const lesson of day.lessons) {
      if (!Number.isFinite(Date.parse(lesson.start_at)) || !Number.isFinite(Date.parse(lesson.end_at)))
        throw new Error("Invalid lesson interval");
      const key = String(lesson.lesson_number);
      if (!slots.has(key)) slots.set(key, []);
      slots.get(key).push(lesson);
    }
    for (const [number, lessons] of slots) {
      const body = lessons.map(l => `${number}-я пара — ${l.subject}${l.room ? ", каб. " + l.room : ""}${l.teacher ? ",\n" + l.teacher : ""}`).join("\n");
      const start = Math.min(...lessons.map(l => Date.parse(l.start_at)));
      add(`${day.date}_lesson_${number}`, "Следующая пара", body, start - settings.lessonNotificationMinutes * 60000);
    }
    if (day.lessons.length) {
      const end = Math.max(...day.lessons.map(l => Date.parse(l.end_at)));
      add(`${day.date}_end`, "Конец учебного дня", `через ${settings.endOfDayNotificationMinutes} минут конец учебного дня`, end - settings.endOfDayNotificationMinutes * 60000);
    }
  }
  const tomorrow = plan.days[1];
  if (tomorrow.complete) {
    const lessons = [...tomorrow.lessons].sort((a, b) => Date.parse(a.start_at) - Date.parse(b.start_at));
    const first = lessons[0];
    const title = first ? `Завтра ${first.lesson_number === 2 ? "ко" : "к"} ${first.lesson_number}-й паре` : "Завтра отдыхаем";
    const body = first ? lessons.map(l => `${l.lesson_number} пара — ${l.subject}`).join("\n") : "пар нет 🎉";
    add(`${plan.days[0].date}_tomorrow`, title, body, plan.summary_at);
  }
  return result;
}

async function syncNotifications(plan, settings, NotificationAPI, now = new Date()) {
  // Fully validate/build before removing anything. A failed HTTP request never gets here.
  const desired = buildNotifications(plan, settings, now);
  const old = (await NotificationAPI.allPending()).filter(n => n.identifier.startsWith(PREFIX));
  await NotificationAPI.removePending(old.map(n => n.identifier));
  for (const item of desired) {
    if (item.date <= new Date()) continue;
    const notification = new NotificationAPI();
    notification.identifier = item.id;
    notification.threadIdentifier = "ceiti_schedule";
    notification.title = item.title;
    notification.body = item.body;
    notification.sound = "default";
    notification.setTriggerDate(item.date);
    await notification.schedule();
  }
  return desired.length;
}

async function main() {
  if (![1, 2].includes(CONFIG.subgroup)) throw new Error("subgroup must be 1 or 2");
  const url = CONFIG.serverUrl.replace(/\/$/, "") + "/api/schedule/plan?group=" + encodeURIComponent(CONFIG.group)
    + "&subgroup=" + CONFIG.subgroup + "&summary_hour=" + CONFIG.tomorrowSummaryHour + "&summary_minute=" + CONFIG.tomorrowSummaryMinute;
  const plan = await loadPlan(url);
  const count = await syncNotifications(plan, CONFIG, Notification);
  console.log(`CEITI: запланировано ${count} уведомлений. Обновлено: ${plan.generated_at}`);
  Script.complete();
}

async function loadPlan(url) {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const request = new Request(url);
      request.timeoutInterval = 60;
      const plan = await request.loadJSON();
      if (!request.response || request.response.statusCode !== 200)
        throw new Error("Server unavailable: " + (request.response?.statusCode || "network"));
      return plan;
    } catch (error) {
      lastError = error;
      console.warn(`CEITI: попытка ${attempt}/3 не удалась: ${error}`);
    }
  }
  throw lastError;
}

// Node export is only for automated tests; Scriptable executes the same functions.
if (typeof Script === "undefined" && typeof module !== "undefined" && module.exports) {
  module.exports = { buildNotifications, syncNotifications };
} else {
  await main();
}
