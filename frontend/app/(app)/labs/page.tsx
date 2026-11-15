import { VenueModule } from "@/components/VenueModule";

export default function LabsPage() {
  return (
    <VenueModule
      type="lab"
      title="Laboratories"
      subtitle="14 labs across computing, electronics, physics, chemistry and mechanical. Eligibility, supervisor presence and safety rules are enforced before a request is held."
      chain={["Lab in-charge", "Head of department"]}
      rules={[
        { rule: "BP-3.1", text: "Only departments listed as eligible may book a lab." },
        { rule: "BP-3.2", text: "A lab that needs a supervisor is booked by faculty or with a faculty sponsor." },
        { rule: "BP-3.5", text: "Chemistry and mechanical labs always need a supervisor for safety." },
        { rule: "BP-3.4", text: "A lab booking lasts at most 180 minutes." },
      ]}
    />
  );
}
