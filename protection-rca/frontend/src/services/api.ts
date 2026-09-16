import axios, { type AxiosInstance } from 'axios';
import type {
  AnalysisJob,
  AuditLogEntry,
  AuthResponse,
  ComtradeFile,
  ConsistencyFinding,
  DashboardStats,
  EvidenceItem,
  Event,
  EventFile,
  FaultCharacteristics,
  FaultClassification,
  Measurement,
  ProtectionOperation,
  RcaHypothesis,
  Report,
  ReviewAction,
  SettingSourceInfo,
  TimelineEntry,
  User,
  WaveformChannelData,
  WaveformMarker,
  PlantTree,
  Substation,
  VoltageLevel,
  Bay,
  Feeder,
  Relay,
  IedContext,
} from '@/types';

const TOKEN_KEY = 'protection_rca_token';
const USER_KEY = 'protection_rca_user';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function storeAuth(token: string, user: User): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function resolveApiBaseURL(): string {
  const fromEnv = String(import.meta.env.VITE_API_BASE_URL || '')
    .trim()
    .replace(/\/$/, '');
  if (fromEnv) return fromEnv;
  // Browser: always same-origin /api (Vite proxy in dev, FastAPI SPA in portable/LAN).
  // Avoid absolute 127.0.0.1 so network clients keep working.
  if (typeof window !== 'undefined') {
    return '/api';
  }
  return 'http://127.0.0.1:8001/api';
}

const baseURL = resolveApiBaseURL();

export const apiClient: AxiosInstance = axios.create({
  baseURL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      clearAuth();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

function apiError(err: unknown, fallback: string): Error {
  const ax = err as {
    code?: string;
    response?: { status?: number; data?: { detail?: string | { msg?: string }[] } };
    message?: string;
  };
  const detail = ax.response?.data?.detail;
  const detailText =
    typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((d) => (typeof d === 'string' ? d : d?.msg || '')).filter(Boolean).join('; ')
        : '';
  if (ax.response?.status === 401 || ax.response?.status === 403) {
    return new Error(detailText || 'Invalid credentials');
  }
  if (ax.response?.status === 429) {
    return new Error(detailText || 'Too many requests — wait about a minute, then retry.');
  }
  if (!ax.response && (ax.message === 'Network Error' || ax.code === 'ERR_NETWORK')) {
    return new Error(
      'Cannot reach the API. Start ProtectionRCA.exe, wait until it is ready, then retry. For LAN access use the host PC IP (not 127.0.0.1) and ensure Windows Firewall allows the port.',
    );
  }
  if (!ax.response) {
    return new Error('Connection failed — API is unreachable');
  }
  return new Error(detailText || ax.message || fallback);
}

export const api = {
  async login(username: string, password: string): Promise<AuthResponse> {
    try {
      const { data } = await apiClient.post<Record<string, unknown>>('/auth/login', {
        username,
        password,
      });
      const accessToken = String(data.access_token ?? '');
      const nested = data.user as User | undefined;
      const user: User = nested ?? {
        id: String(data.user_id ?? 'unknown'),
        username: String(data.username ?? username),
        email: String(data.email ?? ''),
        full_name: (data.full_name as string | undefined) ?? null,
        role: String(data.role ?? 'VIEWER') as User['role'],
        is_active: true,
      };
      const auth: AuthResponse = {
        access_token: accessToken,
        token_type: String(data.token_type ?? 'bearer'),
        user,
      };
      storeAuth(auth.access_token, auth.user);
      return auth;
    } catch (err) {
      throw apiError(err, 'Login failed');
    }
  },

  logout(): void {
    clearAuth();
  },

  async getMe(): Promise<User> {
    const { data } = await apiClient.get<User>('/users/me');
    return data;
  },

  async getDashboardStats(days = 30): Promise<DashboardStats> {
    const { data } = await apiClient.get<DashboardStats>('/dashboard/stats', {
      params: { days },
    });
    return data;
  },

  async getEvents(params?: {
    queue?: string;
    status?: string;
    decision_state?: string;
    data_quality?: string;
    date_from?: string;
    date_to?: string;
    relay_id?: string;
    unmapped?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<Event[]> {
    const { data } = await apiClient.get<Event[] | { items: Event[] }>('/events', {
      params,
    });
    if (Array.isArray(data)) return data;
    return data.items ?? [];
  },

  async getEvent(id: string): Promise<Event> {
    const { data } = await apiClient.get<Event>(`/events/${id}`);
    return data;
  },

  async createEvent(payload: Partial<Event> & Record<string, unknown>): Promise<Event> {
    const { data } = await apiClient.post<Event>('/events', payload);
    return data;
  },

  async getPlantTree(): Promise<PlantTree> {
    const { data } = await apiClient.get<PlantTree>('/plant/tree');
    return data;
  },

  async createSubstation(body: { name: string; code?: string }): Promise<Substation> {
    const { data } = await apiClient.post('/substations', body);
    return data;
  },

  async deleteSubstation(id: string): Promise<void> {
    await apiClient.delete(`/substations/${id}`);
  },

  async createVoltageLevel(body: {
    substation_id: string;
    name: string;
    nominal_voltage_kv?: number;
    code?: string;
  }): Promise<VoltageLevel> {
    const { data } = await apiClient.post('/voltage-levels', body);
    return data;
  },

  async deleteVoltageLevel(id: string): Promise<void> {
    await apiClient.delete(`/voltage-levels/${id}`);
  },

  async createBay(body: {
    voltage_level_id: string;
    name: string;
    code?: string;
  }): Promise<Bay> {
    const { data } = await apiClient.post('/bays', body);
    return data;
  },

  async deleteBay(id: string): Promise<void> {
    await apiClient.delete(`/bays/${id}`);
  },

  async createFeeder(body: {
    bay_id: string;
    name: string;
    code?: string;
  }): Promise<Feeder> {
    const { data } = await apiClient.post('/feeders', body);
    return data;
  },

  async deleteFeeder(id: string): Promise<void> {
    await apiClient.delete(`/feeders/${id}`);
  },

  async createIed(body: {
    feeder_id: string;
    name: string;
    relay_tag?: string;
  }): Promise<Relay> {
    const { data } = await apiClient.post('/ieds', body);
    return data;
  },

  async deleteIed(id: string): Promise<void> {
    await apiClient.delete(`/ieds/${id}`);
  },

  async getIedContext(iedId: string): Promise<IedContext> {
    const { data } = await apiClient.get<IedContext>(`/ieds/${iedId}`);
    return data;
  },

  async deleteEvent(id: string): Promise<void> {
    await apiClient.delete(`/events/${id}`);
  },

  async updateEvent(
    id: string,
    body: {
      substation_name?: string;
      bay_name?: string;
      relay_tag?: string;
      breaker_tag?: string;
      asset_name?: string;
      description?: string;
      feeder?: string;
      nominal_voltage_kv?: number | null;
      nominal_frequency_hz?: number | null;
      extra?: Record<string, unknown>;
    },
  ): Promise<Event> {
    try {
      const { data } = await apiClient.patch<Event>(`/events/${id}`, body);
      return data;
    } catch (err) {
      throw apiError(err, 'Failed to update event');
    }
  },

  async getChannelMap(eventId: string): Promise<{
    event_id: string;
    channel_map: Record<string, string>;
    inferred_roles: Record<string, string>;
    channels: Array<{
      name: string;
      phase?: string | null;
      units?: string | null;
      mapped_signal?: string | null;
      inferred?: string;
      assigned?: string;
    }>;
    valid_roles: string[];
  }> {
    const { data } = await apiClient.get(`/dr/events/${eventId}/channel-map`);
    return data;
  },

  async putChannelMap(eventId: string, channel_map: Record<string, string>) {
    const { data } = await apiClient.put(`/dr/events/${eventId}/channel-map`, { channel_map });
    return data;
  },

  async getDigitalMap(eventId: string): Promise<{
    event_id: string;
    digital_map: Record<string, { role: string; element: string }>;
    channels: Array<{
      name: string;
      phase?: string | null;
      inferred_role?: string;
      inferred_element?: string | null;
      assigned_role?: string;
      assigned_element?: string | null;
    }>;
    valid_roles: string[];
    valid_elements: string[];
  }> {
    const { data } = await apiClient.get(`/dr/events/${eventId}/digital-map`);
    return data;
  },

  async putDigitalMap(
    eventId: string,
    digital_map: Record<string, { role: string; element: string }>,
  ) {
    const { data } = await apiClient.put(`/dr/events/${eventId}/digital-map`, { digital_map });
    return data;
  },

  async getComtradeEnds(eventId: string) {
    const { data } = await apiClient.get(`/dr/events/${eventId}/comtrade-ends`);
    return data as {
      ends: Array<Record<string, unknown>>;
      local?: Record<string, unknown>;
      remote?: Record<string, unknown>;
      computed_sync_offset_us?: number | null;
      multi_end?: Record<string, unknown>;
    };
  },

  async setEndLabel(eventId: string, event_file_id: string, end_label: string) {
    const { data } = await apiClient.post(`/dr/events/${eventId}/end-label`, {
      event_file_id,
      end_label,
    });
    return data;
  },

  async putMultiEnd(
    eventId: string,
    body: {
      local_comtrade_file_id?: string;
      remote_comtrade_file_id?: string;
      sync_offset_us?: number;
    },
  ) {
    const { data } = await apiClient.put(`/dr/events/${eventId}/multi-end`, body);
    return data;
  },

  async ingestSettingsFile(eventId: string, file: File) {
    const form = new FormData();
    form.append('file', file);
    const { data } = await apiClient.post(`/dr/events/${eventId}/settings-ingest`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  async scanWatchFolder(folder?: string) {
    const { data } = await apiClient.get('/dr/watch/scan', {
      params: folder ? { folder } : undefined,
    });
    return data as {
      status: string;
      candidates?: Array<{ path: string; name: string; size: number }>;
      reason?: string;
    };
  },

  async detectComtrade(files: File[]): Promise<Record<string, unknown>> {
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    const { data } = await apiClient.post('/comtrade/detect', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  async validateComtrade(files: File[]): Promise<Record<string, unknown>> {
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    const { data } = await apiClient.post('/comtrade/validate', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  async parseComtrade(files: File[]): Promise<Record<string, unknown>> {
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    const { data } = await apiClient.post('/comtrade/parse', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  async startAnalysis(eventId: string, force = false): Promise<AnalysisJob> {
    try {
      const { data } = await apiClient.post<{ job: AnalysisJob }>(
        '/analyse',
        { event_id: eventId, force },
        { timeout: 60000 },
      );
      return data.job;
    } catch (err) {
      throw apiError(err, 'Failed to start analysis');
    }
  },

  async verifyActiveSettings(eventId: string, note?: string): Promise<Event> {
    try {
      const { data } = await apiClient.post<Event>(
        `/events/${eventId}/verify-active-settings`,
        { confirmed: true, note: note || null },
      );
      return data;
    } catch (err) {
      throw apiError(err, 'Failed to verify active settings');
    }
  },

  async approveSettingsFile(
    eventId: string,
    opts?: { note?: string; alsoVerifyActiveGroup?: boolean },
  ): Promise<Event> {
    try {
      const { data } = await apiClient.post<Event>(`/events/${eventId}/approve-settings`, {
        confirmed: true,
        note: opts?.note || null,
        also_verify_active_group: opts?.alsoVerifyActiveGroup !== false,
      });
      return data;
    } catch (err) {
      throw apiError(err, 'Failed to approve settings file');
    }
  },

  async getEventFiles(eventId: string): Promise<EventFile[]> {
    const { data } = await apiClient.get<EventFile[]>(`/events/${eventId}/files`);
    return data;
  },

  async uploadEventFiles(eventId: string, files: File[]): Promise<EventFile[]> {
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    const { data } = await apiClient.post<EventFile[]>(
      `/events/${eventId}/files`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return data;
  },

  async getComtrade(eventId: string): Promise<ComtradeFile> {
    try {
      const { data } = await apiClient.get<ComtradeFile>(`/events/${eventId}/comtrade`);
      return data;
    } catch (err) {
      throw apiError(
        err,
        'COMTRADE metadata not available. Upload CFG/DAT (or CFF/ZIP), then run analysis.',
      );
    }
  },

  async getWaveforms(
    eventId: string,
    opts?: { comtradeFileId?: string },
  ): Promise<{
    channels: WaveformChannelData[];
    markers: WaveformMarker[];
    note?: string | null;
    comtrade_file_id?: string;
  }> {
    const { data } = await apiClient.get<{
      channels?: Array<{
        name: string;
        channel_type: string;
        phase?: string | null;
        units?: string | null;
        ps?: string | null;
        primary?: number | null;
        secondary?: number | null;
        sample_count?: number | null;
        samples?: number[] | null;
        timestamps_us?: number[] | null;
      }>;
      markers?: WaveformMarker[];
      note?: string | null;
      comtrade_file_id?: string;
    }>(`/events/${eventId}/waveforms`, {
      params: opts?.comtradeFileId ? { comtrade_file_id: opts.comtradeFileId } : undefined,
    });

    const channels: WaveformChannelData[] = (data.channels || [])
      .filter((c) => Array.isArray(c.samples) && c.samples.length > 0)
      .map((c, idx) => {
        const samples = (c.samples || []).map((v) => Number(v) || 0);
        let time_us = (c.timestamps_us || []).map((t) => Number(t) || 0);
        if (time_us.length !== samples.length) {
          time_us = samples.map((_, i) => i);
        }
        return {
          channel: {
            id: `${c.channel_type}-${c.name}-${idx}`,
            comtrade_file_id: data.comtrade_file_id || '',
            channel_index: idx,
            channel_type: (c.channel_type === 'DIGITAL' ? 'DIGITAL' : 'ANALOG') as
              | 'ANALOG'
              | 'DIGITAL',
            name: c.name,
            phase: c.phase,
            units: c.units,
            ps: c.ps ?? null,
            primary: c.primary ?? null,
            secondary_ratio: c.secondary ?? null,
          },
          samples,
          time_us,
        };
      });

    return {
      channels,
      markers: data.markers || [],
      note: data.note,
      comtrade_file_id: data.comtrade_file_id,
    };
  },

  async getTimeline(eventId: string): Promise<TimelineEntry[]> {
    const { data } = await apiClient.get<TimelineEntry[]>(`/events/${eventId}/timeline`);
    return data;
  },

  async getMeasurements(eventId: string): Promise<Measurement[]> {
    const { data } = await apiClient.get<
      Measurement[] | { measurements?: Measurement[] }
    >(`/events/${eventId}/electrical`);
    if (Array.isArray(data)) return data;
    return data.measurements ?? [];
  },

  async getProtection(eventId: string): Promise<ProtectionOperation[]> {
    const { data } = await apiClient.get<
      ProtectionOperation[] | { operations?: ProtectionOperation[] }
    >(`/events/${eventId}/protection`);
    if (Array.isArray(data)) return data;
    return data.operations ?? [];
  },

  async getConsistency(eventId: string): Promise<{
    findings: ConsistencyFinding[];
    setting_source: SettingSourceInfo;
    overall_status: string;
  }> {
    const { data } = await apiClient.get(`/events/${eventId}/consistency`);
    return {
      findings: data.findings ?? [],
      setting_source: data.setting_source ?? {
        source: 'NOT VERIFIED',
        version: 'NOT VERIFIED',
        approval_status: 'NOT VERIFIED',
        active_group_status: 'NOT VERIFIED',
      },
      overall_status: data.overall_status ?? 'NOT_AVAILABLE',
    };
  },

  async getFaultClassification(eventId: string): Promise<FaultClassification> {
    const { data } = await apiClient.get<
      FaultClassification | FaultClassification[]
    >(`/events/${eventId}/fault`);
    if (Array.isArray(data)) {
      if (!data[0]) throw new Error('No fault classification');
      return data[0];
    }
    return data;
  },

  async getFaultCharacteristics(eventId: string): Promise<FaultCharacteristics> {
    const { data } = await apiClient.get<FaultCharacteristics>(
      `/events/${eventId}/fault-characteristics`,
    );
    return data;
  },

  async getRca(eventId: string): Promise<RcaHypothesis[]> {
    const { data } = await apiClient.get<{ hypotheses?: RcaHypothesis[] } | RcaHypothesis[]>(
      `/events/${eventId}/rca`,
    );
    if (Array.isArray(data)) return data;
    return data.hypotheses ?? [];
  },

  async getCauseEvidence(eventId: string): Promise<{
    event_id: string;
    items: Array<{ token: string; source?: string; note?: string | null }>;
    tag_choices: Array<{ token: string; label: string }>;
    asset_type?: string | null;
    enrichment?: Record<string, unknown>;
    scheme?: Record<string, unknown>;
  }> {
    const { data } = await apiClient.get(`/events/${eventId}/cause-evidence`);
    return data;
  },

  async putCauseEvidence(
    eventId: string,
    body: { tokens?: string[]; items?: Array<{ token: string; note?: string }>; notes?: string },
  ) {
    const { data } = await apiClient.put(`/events/${eventId}/cause-evidence`, body);
    return data;
  },

  async getEvidence(eventId: string): Promise<EvidenceItem[]> {
    const { data } = await apiClient.get<
      EvidenceItem[] | { items?: EvidenceItem[] }
    >(`/events/${eventId}/evidence`);
    if (Array.isArray(data)) return data;
    return data.items ?? [];
  },

  async getReport(eventId: string): Promise<Report> {
    const { data } = await apiClient.get<
      Report[] | Report | { items?: Report[]; total?: number }
    >(`/reports/by-event/${eventId}`);
    if (Array.isArray(data)) {
      if (!data[0]) throw new Error('No report available');
      return data[0];
    }
    if (data && typeof data === 'object' && 'items' in data) {
      const first = data.items?.[0];
      if (!first) throw new Error('No report available');
      return first;
    }
    if (data && typeof data === 'object' && 'id' in data) {
      return data as Report;
    }
    throw new Error('No report available');
  },

  async submitReview(
    eventId: string,
    payload: { action: ReviewAction; comments?: string; modifications?: Record<string, unknown> },
  ): Promise<void> {
    await apiClient.post(`/review`, { event_id: eventId, ...payload });
  },

  async getAnalysisStatus(eventId: string): Promise<AnalysisJob> {
    try {
      const { data } = await apiClient.get<AnalysisJob>(`/events/${eventId}/analysis-status`);
      return data;
    } catch {
      const { data } = await apiClient.get<AnalysisJob>(`/analysis-status/${eventId}`);
      return data;
    }
  },

  async getUsers(): Promise<User[]> {
    const { data } = await apiClient.get<User[] | { items: User[] }>('/users');
    return Array.isArray(data) ? data : data.items ?? [];
  },

  async getAuditLog(): Promise<AuditLogEntry[]> {
    const { data } = await apiClient.get<AuditLogEntry[] | { items: AuditLogEntry[] }>('/audit');
    return Array.isArray(data) ? data : data.items ?? [];
  },

  async clearAuditLog(): Promise<{ deleted: number }> {
    const { data } = await apiClient.delete<{ deleted: number }>('/audit');
    return data;
  },
};

export default api;
