export const money = (amount: string, currency = "USD") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(Number(amount));
export const shortName = (title: string) => title.replace(" · Demo Card", "");
