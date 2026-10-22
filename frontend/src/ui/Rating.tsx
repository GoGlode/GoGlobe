import Icon from "./Icon";

export default function Rating({ value, count }: { value: number; count?: number }) {
  return (
    <span className="rating">
      <span className="rating__stars">
        {[1, 2, 3, 4, 5].map((i) => <Icon key={i} name="star" size={15} filled stroke={0} className={value >= i - 0.25 ? "" : "off"} />)}
      </span>
      <span>{value.toFixed(1)}{count ? ` (${count})` : ""}</span>
    </span>
  );
}
