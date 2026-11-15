import { VenueModule } from "@/components/VenueModule";

export default function AmphitheatresPage() {
  return (
    <VenueModule
      type="amphitheatre"
      title="Amphitheatres"
      subtitle="Two large venues with stage, microphones and recording. Audio-visual setup and teardown buffers are kept around every event."
      chain={["Estate office", "Dean (only above 100 attendees)"]}
      rules={[
        { rule: "BP-4.1", text: "Occupancy never exceeds 100 percent of capacity (fire safety)." },
        { rule: "BP-4.2", text: "Events above 100 attendees need Dean approval after estate approval." },
        { rule: "BP-4.3", text: "30 minutes of setup and 30 minutes of teardown surround every event." },
        { rule: "BP-4.4", text: "Below half full the system recommends a smaller venue." },
      ]}
    />
  );
}
