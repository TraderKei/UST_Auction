const fieldGroups = [
  { title: "종류·만기", fields: [["type / securityType", "단기채·중기채·장기채·물가연동채·변동금리채"], ["term / securityTerm", "입찰 만기와 발행 만기"], ["maturityDate", "만기일"], ["reopening / CMB", "재발행 및 특별 단기채 구분"]] },
  { title: "일정·발행 조건", fields: [["announcementDate", "공고일"], ["auctionDate", "입찰일"], ["issueDate", "결제일"], ["closingTimeCompetitive", "경쟁입찰 마감 시각(원문 ET)"], ["offeringAmount", "발행 예정액"]] },
  { title: "낙찰 결과", fields: [["highYield / highDiscountRate", "상품 종류에 맞는 낙찰 기준 금리"], ["highDiscountMargin", "변동금리채 할인마진"], ["bidToCoverRatio", "응찰률 원본 필드 · 화면은 %로 변환"], ["allocationPercentage", "최고 낙찰 기준 값에서의 배정률 후보"]] },
  { title: "참여자별 배정", fields: [["competitiveTendered / Accepted", "경쟁입찰 응찰액·낙찰액"], ["primaryDealerAccepted", "PD 낙찰액"], ["directBidderAccepted", "직접 낙찰액"], ["indirectBidderAccepted", "간접 낙찰액"], ["SOMA / FIMA / retail", "공식기관·비경쟁 배정 참고 항목"]] },
];
const tables = [
  ["security_master", "증권 정보", "종류·만기 등 기준 정보"],
  ["auction", "입찰 일정", "공고·입찰·결제일과 발행 조건"],
  ["auction_result", "낙찰 결과", "응찰률·낙찰 금리 등 결과 값"],
  ["bidder_allocation", "참여자별 배정", "참여자별 응찰액과 낙찰액"],
  ["source_snapshot", "원본 자료", "출처와 수집 시각·원본 응답"],
  ["auction_source_link", "출처 연결", "각 입찰과 원본 자료의 대응 관계"],
];

export default function AuctionReference({ view }: { view: "api" | "database" }) {
  return <>
    <div className="reference-notice">기존 참고 설계입니다. API 정의·수집 주기·DB 구성은 아직 검증·확정하지 않았으며, 실제 수집·저장 기능의 완료를 뜻하지 않습니다.</div>
    <main className="content reference-page">
      <section className="reference-hero"><div><span className="section-kicker">{view === "api" ? "원천 자료와 화면 값의 대응" : "저장 구조 참고안 · 미구현"}</span><h1>{view === "api" ? "API 필드 안내" : "데이터 구조 안내"}</h1><p>{view === "api" ? "기존 코드가 참고하는 필드입니다. 영어 필드명은 API와 대조할 때 필요한 식별 명칭으로 유지합니다. 원문 날짜와 실제 시각은 구분하며, 응찰률은 화면에서 백분율로 표시합니다." : "기존 6개 테이블 설계안을 설명합니다. 실제 DB를 생성한 화면이 아니며, 최종 기술과 구조는 해당 단계에서 결정합니다."}</p></div></section>
      {view === "api" ? <div className="extraction-grid">{fieldGroups.map((group, index) => <article className="field-card" key={group.title}><div className="field-card-head"><span>{index + 1}</span><h2>{group.title}</h2></div>{group.fields.map(([field, text]) => <div className="field-row" key={field}><code>{field}</code><p>{text}</p></div>)}</article>)}</div> : <div className="schema-grid">{tables.map(([name, label, description]) => <article className="schema-card" key={name}><div className="schema-top"><h2>{label}</h2><code>{name}</code></div><p>{description}</p></article>)}</div>}
      <section className="logic-strip"><div><span>01</span><b>값 구분</b><small>자료 없음·미적용·실제 0을 구분합니다.</small></div><div><span>02</span><b>지표 구분</b><small>종류별 낙찰 금리와 배정률·응찰률을 구분합니다.</small></div><div><span>03</span><b>직전 비교</b><small>같은 종류·만기의 이전 입찰과 비교합니다.</small></div><div><span>04</span><b>출처 확인</b><small>필드 정의·이용 조건·갱신 주기를 후속 단계에서 검증합니다.</small></div></section>
    </main>
  </>;
}
