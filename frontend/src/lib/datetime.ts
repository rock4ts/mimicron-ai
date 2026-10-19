const MONTHS = [
  "янв.",
  "февр.",
  "мар.",
  "апр.",
  "мая",
  "июн.",
  "июл.",
  "авг.",
  "сент.",
  "окт.",
  "нояб.",
  "дек.",
];

export function formatDatetime(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const month = MONTHS[date.getMonth()] ?? "";
  const day = String(date.getDate());
  const year = date.getFullYear();
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${day} ${month} ${year} · ${hours}:${minutes}`;
}

export function firstLetter(value: string): string {
  const trimmed = value.trim();
  return trimmed ? trimmed[0]!.toUpperCase() : "?";
}
