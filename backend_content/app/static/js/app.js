function scrollChatToLatest() {
  const log = document.querySelector("[data-chat-log]");
  if (log) {
    log.scrollTop = log.scrollHeight;
  }
}

document.addEventListener("DOMContentLoaded", scrollChatToLatest);

document.addEventListener("htmx:beforeSwap", (event) => {
  const status = event.detail.xhr.status;
  if ([404, 422, 500, 502].includes(status)) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});

document.addEventListener("htmx:afterSettle", () => {
  scrollChatToLatest();
  const invalidField = document.querySelector('[aria-invalid="true"]');
  if (invalidField) {
    invalidField.focus({ preventScroll: true });
  }
});
