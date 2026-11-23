(() => {
  const palette = ["#6c63ff", "#34bfa3", "#f7b84b", "#f4778d", "#55a4e8", "#a57cf4", "#f28e5c", "#8ba0b5"];
  const currency = new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  let expenseChart;
  let cashflowChart;
  let pendingDeleteId = null;
  let allTransactions = [];

  const formatMoney = (value) => currency.format(Number(value) || 0);
  const localISODate = () => {
    const now = new Date();
    const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    return localDate.toISOString().slice(0, 10);
  };
  const showToast = (message, type = "success") => {
    const region = document.querySelector(".toast-region");
    if (!region) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    region.append(toast);
    requestAnimationFrame(() => toast.classList.add("visible"));
    window.setTimeout(() => {
      toast.classList.remove("visible");
      window.setTimeout(() => toast.remove(), 250);
    }, 3500);
  };
  const api = async (url, options = {}) => {
    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "",
        ...options.headers,
      },
      ...options,
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "Something went wrong. Please try again.");
    return result;
  };
  const formatDate = (isoDate) => {
    const value = new Date(`${isoDate}T00:00:00`);
    return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(value);
  };
  const setSummary = (summary) => {
    document.querySelectorAll("[data-summary]").forEach((element) => {
      const key = element.dataset.summary;
      element.textContent = key === "transaction_count"
        ? Number(summary[key] || 0).toLocaleString("en-IN")
        : formatMoney(summary[key]);
    });
  };
  const makeCell = (text, className = "") => {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = text;
    return cell;
  };
  const renderTransaction = (transaction, compact = false) => {
    const row = document.createElement("tr");
    const isIncome = transaction.type === "income";
    if (compact) {
      const details = document.createElement("td");
      const title = document.createElement("div");
      title.className = "transaction-title";
      title.textContent = transaction.description;
      const type = document.createElement("span");
      type.className = `transaction-subtitle ${isIncome ? "text-income" : "text-expense"}`;
      type.textContent = isIncome ? "Income" : "Expense";
      details.append(title, type);
      row.append(details, makeCell(formatDate(transaction.date)), makeCell(transaction.category));
      row.append(makeCell(`${isIncome ? "+" : "−"} ${formatMoney(transaction.amount)}`, `amount-cell align-right ${isIncome ? "amount-income" : "amount-expense"}`));
      return row;
    }

    row.append(makeCell(formatDate(transaction.date)));
    const details = document.createElement("td");
    const title = document.createElement("div");
    title.className = "transaction-title";
    title.textContent = transaction.description;
    details.append(title);
    row.append(details, makeCell(transaction.category));
    const typeCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `type-badge ${isIncome ? "type-income" : "type-expense"}`;
    badge.textContent = isIncome ? "Income" : "Expense";
    typeCell.append(badge);
    row.append(typeCell, makeCell(`${isIncome ? "+" : "−"} ${formatMoney(transaction.amount)}`, `amount-cell align-right ${isIncome ? "amount-income" : "amount-expense"}`));
    const actions = document.createElement("td");
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "icon-button delete-transaction";
    deleteButton.dataset.transactionId = String(transaction.id);
    deleteButton.setAttribute("aria-label", `Delete ${transaction.description}`);
    deleteButton.title = "Delete transaction";
    deleteButton.textContent = "⌫";
    actions.append(deleteButton);
    row.append(actions);
    return row;
  };
  const renderRecent = (transactions) => {
    const body = document.querySelector("#recent-transactions");
    if (!body) return;
    body.replaceChildren();
    if (!transactions.length) {
      const row = document.createElement("tr");
      row.append(makeCell("No transactions yet. Add your first income or expense.", "table-empty"));
      row.firstChild.colSpan = 4;
      body.append(row);
      return;
    }
    transactions.forEach((transaction) => body.append(renderTransaction(transaction, true)));
  };
  const renderAllTransactions = (transactions) => {
    const body = document.querySelector("#all-transactions");
    if (!body) return;
    const type = document.querySelector("#type-filter")?.value || "all";
    const query = (document.querySelector("#transaction-search")?.value || "").trim().toLowerCase();
    const visible = transactions.filter((item) => {
      const matchesType = type === "all" || item.type === type;
      const matchesQuery = [item.description, item.category, item.date, item.type]
        .some((value) => String(value).toLowerCase().includes(query));
      return matchesType && matchesQuery;
    });
    body.replaceChildren();
    const count = document.querySelector("#transaction-total");
    if (count) count.textContent = transactions.length.toLocaleString("en-IN");
    if (!visible.length) {
      const row = document.createElement("tr");
      row.append(makeCell(transactions.length ? "No transactions match your search." : "No transactions yet.", "table-empty"));
      row.firstChild.colSpan = 6;
      body.append(row);
      return;
    }
    visible.forEach((transaction) => body.append(renderTransaction(transaction)));
  };
  const renderCategoryReport = (categories) => {
    const container = document.querySelector("#category-report-list");
    if (!container) return;
    container.replaceChildren();
    if (!categories.length) {
      const empty = document.createElement("p");
      empty.className = "table-empty";
      empty.textContent = "No expenses recorded yet.";
      container.append(empty);
      return;
    }
    const max = Math.max(...categories.map((item) => item.amount));
    categories.forEach((item, index) => {
      const line = document.createElement("div");
      line.className = "category-report-row";
      const heading = document.createElement("div");
      heading.className = "category-report-heading";
      const name = document.createElement("strong");
      name.textContent = item.category;
      const amount = document.createElement("span");
      amount.textContent = formatMoney(item.amount);
      heading.append(name, amount);
      const track = document.createElement("div");
      track.className = "progress-track";
      const bar = document.createElement("span");
      bar.style.width = `${Math.max((item.amount / max) * 100, 2)}%`;
      bar.style.backgroundColor = palette[index % palette.length];
      track.append(bar);
      line.append(heading, track);
      container.append(line);
    });
  };
  const renderCharts = (categories, monthly) => {
    const pie = document.querySelector("#expense-chart");
    const bar = document.querySelector("#cashflow-chart");
    if (!pie && !bar) return;
    const legend = document.querySelector("#category-legend");
    const pieEmpty = document.querySelector('[data-empty="expense-chart"]');
    const barEmpty = document.querySelector('[data-empty="cashflow-chart"]');
    if (legend) legend.replaceChildren();

    if (pie) {
      if (expenseChart) expenseChart.destroy();
      const hasData = categories.length > 0;
      pie.hidden = !hasData;
      if (pieEmpty) pieEmpty.hidden = hasData;
      if (window.Chart && hasData) {
        expenseChart = new Chart(pie, {
          type: "doughnut",
          data: {
            labels: categories.map((item) => item.category),
            datasets: [{ data: categories.map((item) => item.amount), backgroundColor: categories.map((_, index) => palette[index % palette.length]), borderWidth: 0, hoverOffset: 5 }],
          },
          options: { cutout: "72%", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (context) => ` ${context.label}: ${formatMoney(context.raw)}` } } }, maintainAspectRatio: false },
        });
      } else if (hasData && pieEmpty) {
        pieEmpty.hidden = false;
        pieEmpty.textContent = "Chart library unavailable";
      }
      if (legend) categories.forEach((item, index) => {
        const line = document.createElement("div");
        line.className = "legend-line";
        const name = document.createElement("span");
        name.className = "legend-name";
        const swatch = document.createElement("i");
        swatch.style.backgroundColor = palette[index % palette.length];
        name.append(swatch, document.createTextNode(item.category));
        const amount = document.createElement("strong");
        amount.textContent = formatMoney(item.amount);
        line.append(name, amount);
        legend.append(line);
      });
    }
    if (bar) {
      if (cashflowChart) cashflowChart.destroy();
      const hasData = monthly.some((item) => item.income || item.expenses);
      bar.hidden = !hasData;
      if (barEmpty) barEmpty.hidden = hasData;
      if (window.Chart && hasData) {
        cashflowChart = new Chart(bar, {
          type: "bar",
          data: {
            labels: monthly.map((item) => new Intl.DateTimeFormat("en", { month: "short" }).format(new Date(`${item.month}-01T00:00:00`))),
            datasets: [
              { label: "Income", data: monthly.map((item) => item.income), backgroundColor: "#6c63ff", borderRadius: 5, maxBarThickness: 24 },
              { label: "Expenses", data: monthly.map((item) => item.expenses), backgroundColor: "#c5c0ff", borderRadius: 5, maxBarThickness: 24 },
            ],
          },
          options: {
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (context) => ` ${context.dataset.label}: ${formatMoney(context.raw)}` } } },
            scales: {
              x: { grid: { display: false }, border: { display: false }, ticks: { color: "#8992a5", font: { family: "DM Sans", size: 11 } } },
              y: { beginAtZero: true, grid: { color: "#eff1f6" }, border: { display: false }, ticks: { color: "#8992a5", maxTicksLimit: 5, callback: (value) => `₹${Number(value).toLocaleString("en-IN")}` } },
            },
          },
        });
      } else if (hasData && barEmpty) {
        barEmpty.hidden = false;
        barEmpty.textContent = "Chart library unavailable";
      }
    }
  };
  const loadDashboard = async () => {
    const data = await api("/api/dashboard");
    setSummary(data.summary);
    renderRecent(data.recent_transactions);
    renderCharts(data.categories, data.monthly);
    renderCategoryReport(data.categories);
    return data;
  };

  document.addEventListener("DOMContentLoaded", async () => {
    const today = document.querySelector("[data-today]");
    if (today) today.textContent = new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(new Date());
    document.querySelectorAll('input[type="date"]').forEach((input) => { if (!input.value) input.value = localISODate(); });

    const menuButton = document.querySelector(".mobile-menu");
    menuButton?.addEventListener("click", () => {
      const sidebar = document.querySelector(".sidebar");
      const opened = sidebar.classList.toggle("sidebar-open");
      menuButton.setAttribute("aria-expanded", String(opened));
    });
    document.querySelectorAll(".main-nav a").forEach((link) => link.addEventListener("click", () => {
      document.querySelector(".sidebar")?.classList.remove("sidebar-open");
      menuButton?.setAttribute("aria-expanded", "false");
    }));

    document.querySelectorAll(".entry-form").forEach((form) => form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      const formData = new FormData(form);
      const payload = Object.fromEntries(formData.entries());
      button.disabled = true;
      try {
        const result = await api(form.dataset.endpoint, { method: "POST", body: JSON.stringify(payload) });
        form.reset();
        form.querySelectorAll('input[type="date"]').forEach((input) => { input.value = localISODate(); });
        showToast(result.message);
        await refreshPageData();
      } catch (error) {
        showToast(error.message, "error");
      } finally {
        button.disabled = false;
      }
    }));

    const search = document.querySelector("#transaction-search");
    const filter = document.querySelector("#type-filter");
    search?.addEventListener("input", () => renderAllTransactions(allTransactions));
    filter?.addEventListener("change", () => renderAllTransactions(allTransactions));

    const dialog = document.querySelector("#delete-dialog");
    document.addEventListener("click", (event) => {
      const button = event.target.closest(".delete-transaction");
      if (!button) return;
      pendingDeleteId = button.dataset.transactionId;
      if (dialog?.showModal) dialog.showModal();
      else if (window.confirm("Delete this transaction? This action cannot be undone.")) deletePendingTransaction();
    });
    document.querySelector("[data-cancel-delete]")?.addEventListener("click", () => dialog.close());
    document.querySelector("[data-confirm-delete]")?.addEventListener("click", async () => {
      dialog.close();
      await deletePendingTransaction();
    });

    try {
      const data = await loadDashboard();
      if (document.querySelector("#all-transactions")) {
        allTransactions = await api("/api/transactions");
        renderAllTransactions(allTransactions);
      }
      if (document.querySelector("#cashflow-chart") && document.querySelector(".report-bar-wrap")) {
        const monthly = await api("/api/reports/monthly");
        renderCharts(data.categories, monthly);
      }
    } catch (error) {
      showToast(error.message, "error");
      renderRecent([]);
    }
  });

  async function deletePendingTransaction() {
    if (!pendingDeleteId) return;
    try {
      const result = await api(`/api/transactions/${pendingDeleteId}`, { method: "DELETE" });
      showToast(result.message);
      pendingDeleteId = null;
      await refreshPageData();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function refreshPageData() {
    try {
      const data = await loadDashboard();
      if (document.querySelector("#all-transactions")) {
        allTransactions = await api("/api/transactions");
        renderAllTransactions(allTransactions);
      }
      if (document.querySelector(".report-bar-wrap")) {
        const monthly = await api("/api/reports/monthly");
        renderCharts(data.categories, monthly);
      }
    } catch (error) {
      showToast(error.message, "error");
    }
  }
})();
