const parseForm = document.getElementById("parse-form");
const textInput = document.getElementById("text");
const resultEl = document.getElementById("result");
const recordsEl = document.getElementById("records");
const refreshBtn = document.getElementById("refresh-btn");
const keyForm = document.getElementById("key-form");
const apiKeyInput = document.getElementById("api-key");

const API_KEY_STORAGE_KEY = "auto_ledger_api_key";

function fmtDate(value) {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function renderRecords(records) {
  if (!records.length) {
    recordsEl.innerHTML = "<li>暂无记录</li>";
    return;
  }

  recordsEl.innerHTML = records
    .map((item) => {
      const amountCls = item.direction === "income" ? "amount-income" : "amount-expense";
      const sign = item.direction === "income" ? "+" : "-";
      return `
        <li>
          <div><strong>${item.category}</strong> - ${item.note || "(无备注)"}</div>
          <div class="meta">
            <span>${fmtDate(item.occurred_at)}</span>
            <span class="${amountCls}">${sign}${item.amount.toFixed(2)} ${item.currency}</span>
          </div>
        </li>
      `;
    })
    .join("");
}

function getApiKey() {
  return (localStorage.getItem(API_KEY_STORAGE_KEY) || "").trim();
}

function authHeaders(extra = {}) {
  const key = getApiKey();
  if (!key) return extra;
  return { ...extra, "X-API-Key": key };
}

async function fetchJson(url, options = {}) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const message = data.detail || data.error || "请求失败";
    throw new Error(message);
  }
  return data;
}

async function loadRecords() {
  try {
    const data = await fetchJson("/api/records?limit=50", {
      headers: authHeaders(),
    });
    renderRecords(data);
  } catch (error) {
    recordsEl.innerHTML = `<li>加载失败：${error.message}</li>`;
  }
}

parseForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = textInput.value.trim();
  if (!text) return;

  resultEl.textContent = "正在解析...";
  try {
    const data = await fetchJson("/api/parse", {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text, source: "web" }),
    });
    const directionText = data.direction === "income" ? "收入" : "支出";
    resultEl.textContent = `已入账：${directionText} ${data.amount.toFixed(2)} 元（${data.category}）`;
    textInput.value = "";
    await loadRecords();
  } catch (error) {
    resultEl.textContent = `失败：${error.message}`;
    return;
  }
});

keyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const key = apiKeyInput.value.trim();
  if (key) {
    localStorage.setItem(API_KEY_STORAGE_KEY, key);
  } else {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
  }
  resultEl.textContent = key ? "API Key 已保存" : "已清除 API Key";
  await loadRecords();
});

apiKeyInput.value = getApiKey();
refreshBtn.addEventListener("click", loadRecords);
loadRecords();
