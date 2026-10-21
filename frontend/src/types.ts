export interface Employee { id: number; name: string }
export interface Rules { unconfirmed_hours: number; dispatch_hours: number; high_value_rupees: number; follow_up_hours: number }
export interface Task {
  id: number; order_id: string; category: string; customer_name: string; phone: string; order_value: number;
  reason: string; priority: string; assigned_employee: string; recommended_action: string; deadline: string;
  status: string; condition_active: boolean; first_detected_at: string; resolved_at: string | null; overdue: boolean;
}
export interface Order {
  id: string; order_date: string; customer_name: string; phone: string; order_value: number; status: string;
  payment_type: string; assigned_employee: string; dispatch_date: string | null; expected_delivery_date: string | null;
  confirmed_at: string | null; source_filename: string; source_row: number;
}
export interface Issue {
  id: number; filename: string; row_number: number; order_id: string | null; field: string; explanation: string;
  recommended_correction: string; severity: string; status: string; raw_record: Record<string,string>;
}
export interface Batch {
  id: number; filename: string; created_at: string; total_rows: number; inserted: number; updated: number;
  unchanged: number; rejected: number; duplicate_rows: number; created_tasks?: number; issue_count?: number;
}
export interface Audit {
  id: number; order_id: string | null; task_id: number | null; responsible_user: string; action: string;
  timestamp: string; details: Record<string,unknown>;
}
export interface Dashboard {
  uploaded_rows: number; unique_orders_all_time: number; unique_orders: number; orders_requiring_attention: number;
  open_tasks: number; overdue_tasks: number; data_issues: number;
  exceptions_by_category: { category: string; name: string; count: number }[];
  employee_pending: { name: string; count: number }[];
  daily_detections: { date: string; count: number }[]; immediate_cases: Task[]; as_of: string;
}
export interface Filters { date_from: string; date_to: string; category: string; employee: string; priority: string; status: string; search: string; overdue: string }
