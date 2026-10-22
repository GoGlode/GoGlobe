import Icon from "./Icon";
import PageHeader from "./PageHeader";

export default function ComingSoon({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <div className="page" style={{ textAlign: "center", paddingTop: 80 }}>
        <div className="circle-btn" style={{ margin: "0 auto 16px", width: 64, height: 64 }}><Icon name="sparkle" size={28} /></div>
        <p className="muted">Экран в разработке</p>
      </div>
    </>
  );
}
