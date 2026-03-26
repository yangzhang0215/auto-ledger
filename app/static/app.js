const parseForm = document.getElementById("parse-form");
const textInput = document.getElementById("text");
const resultEl = document.getElementById("result");
const recordsEl = document.getElementById("records");
const refreshBtn = document.getElementById("refresh-btn");

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
    const data = await fetchJson("/api/records?limit=50");
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
      headers: { "Content-Type": "application/json" },
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
refreshBtn.addEventListener("click", loadRecords);
loadRecords();
