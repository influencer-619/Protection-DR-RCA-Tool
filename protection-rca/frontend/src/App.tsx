import { Navigate, Route, Routes } from 'react-router-dom';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { AppLayout } from '@/layouts/AppLayout';
import { EventLayout } from '@/layouts/EventLayout';
import { LoginPage } from '@/pages/LoginPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { EventsListPage } from '@/pages/EventsListPage';
import { EventOverviewPage } from '@/pages/EventOverviewPage';
import { EventSummaryPage } from '@/pages/EventSummaryPage';
import { EventFilesPage } from '@/pages/EventFilesPage';
import { EventComtradePage } from '@/pages/EventComtradePage';
import { WaveformPage } from '@/pages/WaveformPage';
import { TimelinePage } from '@/pages/TimelinePage';
import { FaultCharacteristicsPage } from '@/pages/FaultCharacteristicsPage';
import { FaultLocationPage } from '@/pages/FaultLocationPage';
import { ElectricalPage } from '@/pages/ElectricalPage';
import { ProtectionPage } from '@/pages/ProtectionPage';
import { ConsistencyPage } from '@/pages/ConsistencyPage';
import { RcaPage } from '@/pages/RcaPage';
import { EvidencePage } from '@/pages/EvidencePage';
import { ReportPage } from '@/pages/ReportPage';
import { ReviewPage } from '@/pages/ReviewPage';
import { UploadPage } from '@/pages/UploadPage';
import { UsersPage } from '@/pages/UsersPage';
import { AuditPage } from '@/pages/AuditPage';
import { CreateEventPage } from '@/pages/CreateEventPage';
import { HelpPage } from '@/pages/HelpPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedRoute />}>
        <Route path="/events/:id/waveforms/popout" element={<WaveformPage popout />} />

        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/events" element={<EventsListPage />} />
          <Route path="/events/new" element={<CreateEventPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/audit" element={<AuditPage />} />

          <Route path="/events/:id" element={<EventLayout />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<EventOverviewPage />} />
            <Route path="summary" element={<EventSummaryPage />} />
            <Route path="files" element={<EventFilesPage />} />
            <Route path="comtrade" element={<EventComtradePage />} />
            <Route path="waveforms" element={<WaveformPage />} />
            <Route path="timeline" element={<TimelinePage />} />
            <Route path="fault-characteristics" element={<FaultCharacteristicsPage />} />
            <Route path="fault-location" element={<FaultLocationPage />} />
            <Route path="electrical" element={<ElectricalPage />} />
            <Route path="protection" element={<ProtectionPage />} />
            <Route path="consistency" element={<ConsistencyPage />} />
            <Route path="rca" element={<RcaPage />} />
            <Route path="evidence" element={<EvidencePage />} />
            <Route path="report" element={<ReportPage />} />
            <Route path="review" element={<ReviewPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" />} />
    </Routes>
  );
}
