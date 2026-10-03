(function () {
  "use strict";

  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  let lastDialogTrigger = null;

  function setPageTitle() {
    const title = document.body.dataset.pageTitle;
    if (title) document.title = `${title} — DataLens Agent`;
  }

  function activateTabs() {
    qsa('[role="tablist"]').forEach((list) => {
      const tabs = qsa('[role="tab"]', list);
      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => selectTab(tab, tabs));
        tab.addEventListener("keydown", (event) => {
          if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
          tabs[next].focus();
          selectTab(tabs[next], tabs);
        });
      });
    });
  }

  function selectTab(tab, tabs) {
    tabs.forEach((item) => {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      const panel = document.getElementById(item.getAttribute("aria-controls"));
      if (panel) panel.hidden = !selected;
    });
  }

  function openDialog(id, trigger) {
    const layer = document.getElementById(id);
    if (!layer) return;
    lastDialogTrigger = trigger;
    layer.classList.add("is-open");
    layer.setAttribute("aria-hidden", "false");
    const target = qs("[data-dialog-cancel], button, input", layer);
    if (target) target.focus();
  }

  function closeDialog(layer) {
    layer.classList.remove("is-open");
    layer.setAttribute("aria-hidden", "true");
    if (lastDialogTrigger) lastDialogTrigger.focus();
  }

  function bindDialogs() {
    qsa("[data-dialog-open]").forEach((button) => button.addEventListener("click", () => openDialog(button.dataset.dialogOpen, button)));
    qsa("[data-dialog]").forEach((layer) => {
      qsa("[data-dialog-close], [data-dialog-cancel]", layer).forEach((button) => button.addEventListener("click", () => closeDialog(layer)));
      layer.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDialog(layer); });
    });
  }

  function showToast(message) {
    let region = qs("#toast-region");
    if (!region) {
      region = document.createElement("div");
      region.id = "toast-region";
      region.className = "toast-region";
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    region.prepend(toast);
    while (region.children.length > 3) region.lastElementChild.remove();
    window.setTimeout(() => toast.remove(), 4000);
  }

  function bindPrototypeActions() {
    qsa("[data-toast]").forEach((button) => button.addEventListener("click", () => showToast(button.dataset.toast)));
    qsa("[data-toggle-target]").forEach((button) => button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.toggleTarget);
      if (!target) return;
      target.hidden = !target.hidden;
      button.setAttribute("aria-expanded", String(!target.hidden));
    }));
    qsa("[data-password-toggle]").forEach((button) => button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "隐藏" : "显示";
      button.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
    }));
    qsa("[data-search-clear]").forEach((button) => button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.searchClear);
      if (input) { input.value = ""; input.focus(); }
    }));
    qsa("[data-prototype-submit]").forEach((form) => form.addEventListener("submit", (event) => {
      event.preventDefault();
      showToast(form.dataset.successMessage || "原型操作已完成（未保存真实数据）");
    }));
  }

  window.prototypeButtonClick = function (button) {
    const delegated = button.matches('[role="tab"], [type="submit"], [data-dialog-open], [data-dialog-close], [data-dialog-cancel], [data-toast], [data-toggle-target], [data-password-toggle], [data-search-clear]');
    if (!delegated && !button.disabled) {
      showToast(`原型操作：${button.textContent.trim()}（未连接真实服务）`);
    }
    return true;
  };

  setPageTitle();
  activateTabs();
  bindDialogs();
  bindPrototypeActions();
})();
