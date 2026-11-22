import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { NotificationsClient } from "@/components/dashboard/notifications/NotificationsClient";

export const metadata: Metadata = { title: "Notifications" };

export default function Page() {
  return (
    <>
      <PageTitle title="Notifications" sub="Alerts about things in your own records. Nothing is created until you switch an alert on, and everything stays in the app: no email or push is sent." />
      <NotificationsClient />
    </>
  );
}
