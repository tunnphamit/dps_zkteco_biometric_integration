# -*- coding: utf-8 -*-
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2024 DOTSPRIME SYSTEM LLP
#    Email : sales@dotsprime.com / dotsprime@gmail.com
########################################################

from odoo import api, fields, models, _
from datetime import datetime
from odoo.exceptions import UserError, ValidationError
from convertdate import islamic


class ZktecoDeviceLogs(models.Model):
    """
    Model to store attendance log records fetched from biometric devices.

    Each log entry represents a punch action such as Check In, Check Out, or Punched.
    The model ensures that logs once calculated cannot be deleted to maintain
    accurate payroll and attendance history.
    """
    _name = 'zkteco.device.logs'
    _order = 'user_punch_time desc'
    _rec_name = 'user_punch_time'

    status = fields.Selection(
        [
            ('0', 'Check In'),
            ('1', 'Check Out'),
            ('2', 'Punched')
        ],
        string='Status',
        help="Represents the type of punch recorded from the device."
    )
    user_punch_time = fields.Datetime(
        string='Punching Time',
        help="The exact datetime when the punch action was recorded."
    )
    user_punch_calculated = fields.Boolean(
        string='Punch Calculated',
        default=False,
        help="Indicates whether this record has already been processed in attendance calculations."
    )
    device = fields.Char(
        string='Device',
        help="The device from which this punch was captured."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        readonly=True,
        default=lambda self: self.env.company,
        help="The company associated with this attendance log."
    )
    zketco_duser_id = fields.Many2one(
        'zkteco.attendance.machine',
        string="Device User",
        help="Reference to the device user linked to this punch record."
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        related='zketco_duser_id.employee_id',
        store=True,
        help="Employee linked to this device user."
    )
    employee_code = fields.Char(
        string='Employee Code',
        related='zketco_duser_id.employee_id.x_studio_m_nhn_vin',
        help="Code of the employee fetched from the linked employee record."
    )
    employee_name = fields.Char(
        string='Employee Name',
        related='zketco_duser_id.employee_id.name',
        help="Name of the employee fetched from the linked employee record."
    )
    status_number = fields.Char(
        string="Status Number",
        help="Raw status code received from the device."
    )
    number = fields.Char(
        string="Number",
        help="Identifier number from the device."
    )
    timestamp = fields.Integer(
        string="Timestamp",
        help="Numeric timestamp representation of the punch."
    )
    punch_status_in_string = fields.Char(
        string="Status String",
        help="Status text representation captured from the device."
    )

    def unlink(self):

        already_processed_logs = self.filtered(lambda record: record.user_punch_calculated)
        if already_processed_logs:
            raise UserError(
                _("You cannot delete attendance logs that are already processed. "
                  "Please contact your administrator if you believe this is incorrect.")
            )
        return super(ZktecoDeviceLogs, self).unlink()
    
    # Customized by Tunn
    @api.model
    def create(self, vals):
        """Khi có log mới, tự động tạo / cập nhật bản ghi hr.attendance."""
        record = super().create(vals)

        employee = record.employee_id
        punch_time = record.user_punch_time

        if not employee or not punch_time:
            return record

        # Tìm bản ghi chấm công gần nhất của nhân viên
        hr_attendance_model = self.env['hr.attendance']
        last_attendance = hr_attendance_model.search([
            ('employee_id', '=', employee.id)
        ], order='check_in desc', limit=1)

        if not last_attendance or last_attendance.check_out:
            # Nếu chưa có hoặc đã check_out → tạo mới Check In
            hr_attendance_model.create({
                'employee_id': employee.id,
                'check_in': punch_time
            })
            record.status = '0'  # Check In
        else:
            # Nếu có bản ghi check_in chưa có check_out
            if punch_time > last_attendance.check_in:
                last_attendance.write({'check_out': punch_time})
                record.status = '1'  # Check Out
            else:
                # Nếu thời gian nhỏ hơn check_in gần nhất → bỏ qua (log cũ)
                record.status = '2'

        return record


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    punch_date = fields.Date(string='Punch Date')

    is_multiple_shift = fields.Boolean(string="Is Multiple Shift", copy=False, store=True,
                                       compute='_compute_multiple_shifts')

    break_time_ms = fields.Float(string="Break Time", compute="_compute_ms_fields", store=True, copy=False)
    worked_hours_ms = fields.Float(string="Worked Hours", compute="_compute_ms_fields", store=True, copy=False)
    actual_worked_hours_ms = fields.Float(string="Actual Worked Hours", compute="_compute_ms_fields", store=True,
                                          copy=False)
    overtime_hours_ms = fields.Float(string="Overtime Hours", compute="_compute_ms_fields", store=True, copy=False)
    shortfall_hours_ms = fields.Float(string="Shortfall Hours", compute="_compute_ms_fields", store=True, copy=False)

    shortfall = fields.Float(string='Shortfall Hours', compute='_compute_shortfall', store=True)
    leave_type = fields.Selection([
        ('none', 'None'),
        ('holiday', 'Holiday'),
        ('medical', 'Medical Leave'),
        ('vacation', 'Vacation'),
    ], string="Leave Type", default='none', required=True)

    def is_in_ramadan(self, punch_date):
        """Convert the Gregorian date to the Islamic (Hijri) calendar.
        Check if the month is Ramadan (9th month in the Islamic calendar)"""
        hijri_year, hijri_month, hijri_day = islamic.from_gregorian(
            punch_date.year, punch_date.month, punch_date.day)
        return hijri_month == 9

    def _get_employee_calendar(self):
        self.ensure_one()
        if self.is_in_ramadan(self.check_in) or self.is_in_ramadan(
                self.check_out) and self.employee_id:
            return self.employee_id.ramadan_resource_calendar_id
        return super()._get_employee_calendar()

    @api.depends('worked_hours', 'employee_id')
    def _compute_shortfall(self):
        for attendance in self:
            attendance.shortfall = False
            if attendance.worked_hours and attendance.employee_id:
                calendar = attendance._get_employee_calendar()
                working_hours = sum(calendar.attendance_ids.filtered(
                    lambda x: x.dayofweek == str(attendance.check_in.weekday())
                ).mapped('duration_hours'))
                if working_hours > attendance.worked_hours:
                    attendance.shortfall = 2 * (working_hours - attendance.worked_hours)

    @api.depends(
        'multiple_checkin_ids.break_time',
        'multiple_checkin_ids.worked_hours',
        'multiple_checkin_ids.actual_worked_hours',
        'employee_id.resource_calendar_id.working_hours'
    )
    def _compute_ms_fields(self):
        for record in self:
            total_break_time = sum(record.multiple_checkin_ids.mapped('break_time'))
            total_worked_hours = sum(record.multiple_checkin_ids.mapped('worked_hours'))
            total_actual_worked_hours = sum(record.multiple_checkin_ids.mapped('actual_worked_hours'))

            record.break_time_ms = round(total_break_time, 2)
            record.worked_hours_ms = round(total_worked_hours, 2)
            record.actual_worked_hours_ms = round(total_actual_worked_hours, 2)

            record.overtime_hours_ms = 0.0
            record.shortfall_hours_ms = 0.0

            working_hours = record.employee_id.resource_calendar_id.working_hours

            if working_hours:
                difference = round(record.actual_worked_hours_ms - working_hours, 2)
                if difference > 0:
                    record.overtime_hours_ms = difference
                    record.shortfall_hours_ms = 0.0
                elif difference < 0:
                    record.shortfall_hours_ms = abs(difference)
                    record.overtime_hours_ms = 0.0
                else:
                    record.overtime_hours_ms = 0.0
                    record.shortfall_hours_ms = 0.0

    @api.depends()
    def _compute_multiple_shifts(self):

        config_value = self.env['ir.config_parameter'].sudo().get_param(
            'dps_zkteco_biometric_integration.multiple_shift'
        )
        is_multi_shift_enabled = config_value in ['True', 'true', '1']
        for rec in self:
            rec.is_multiple_shift = True if is_multi_shift_enabled else False

    def _get_multiple_shift_status(self):

        config_value = self.env['ir.config_parameter'].sudo().get_param(
            'dps_zkteco_biometric_integration.multiple_shift'
        )
        return config_value in ['True', 'true', '1']

    @api.model
    def create(self, values):

        if 'is_multiple_shift' not in values:
            values['is_multiple_shift'] = self._get_multiple_shift_status()
        try:
            return super(HrAttendance, self).create(values)
        except Exception as e:
            # Raise a professional error message if record creation fails
            raise UserError(
                f"Unable to create record. Reason: {str(e)}"
            )

    def write(self, values):

        if 'is_multiple_shift' not in values:
            values['is_multiple_shift'] = self._get_multiple_shift_status()
        try:
            return super(HrAttendance, self).write(values)
        except Exception as e:
            raise UserError(
                f"Unable to update record(s). Reason: {str(e)}"
            )

    check_in_check_out_difference = fields.Float('Punching Difference', compute='check_in_check_out_diff')

    def check_in_check_out_diff(self):

        for record in self:
            try:
                if record.check_in and record.check_out:
                    start_time = datetime.strptime(str(record.check_in), '%Y-%m-%d %H:%M:%S')
                    end_time = datetime.strptime(str(record.check_out), '%Y-%m-%d %H:%M:%S')

                    if end_time < start_time:
                        raise ValidationError(
                            "Invalid attendance entry: Check-out time cannot be earlier than check-in time."
                        )

                    duration_seconds = (end_time - start_time).seconds

                    duration_hours = duration_seconds / 3600.0

                    record.check_in_check_out_difference = duration_hours
                else:
                    record.check_in_check_out_difference = 0

            except ValueError:
                raise UserError(
                    "Attendance record contains an invalid date format. "
                    "Please ensure check-in and check-out are properly set."
                )

    def unlink(self):

        try:
            for attendance_rec in self:
                log_search_domain = [
                    ('employee_id', '=', attendance_rec.employee_id.id),
                    '|',
                    ('user_punch_time', '=', attendance_rec.check_in),
                    ('user_punch_time', '=', attendance_rec.check_out)
                ]

                related_logs = self.env['zkteco.device.logs'].search(log_search_domain)

                for log_entry in related_logs:
                    log_entry.user_punch_calculated = False

            return super(HrAttendance, self).unlink()

        except (UserError, ValidationError) as e:
            raise UserError(
                "An error occurred while deleting attendance records. "
                f"Details: {str(e)}"
            )
        except Exception as e:
            raise UserError(
                "A system error occurred while processing the deletion of attendance records. "
                "Please contact the system administrator. "
                f"Error details: {str(e)}"
            )


class EmployeeLeaveLine(models.Model):
    _name = 'employee.leave.line'
    _description = 'Employee Leave Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    employee_id = fields.Many2one('hr.employee', string="Employee", required=True, ondelete='cascade', tracking=True)
    date = fields.Date(string="Date", required=True, tracking=True)
    leave_type = fields.Selection([
        ('none', 'None'),
        ('holiday', 'Holiday'),
        ('medical', 'Medical Leave'),
        ('vacation', 'Vacation'),
    ], string="Leave Type", default='none', required=True, tracking=True)
    att_start_date = fields.Datetime(string="Start", store=True)
    att_end_date = fields.Datetime(string="End", store=True)
    paid_medical_leave = fields.Boolean(string='Paid')


    description = fields.Char(string="Description")

    def _log_change_on_employee(self, message):
        for rec in self:
            if rec.employee_id:
                rec.employee_id.message_post(
                    body=message,
                    subtype_xmlid="mail.mt_note",
                )

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec._log_change_on_employee(f"➕ Leave entry created: {rec.date} – {rec.leave_type.capitalize()}")
        return rec

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            rec._log_change_on_employee(f"✏️ Leave entry updated: {rec.date} – {rec.leave_type.capitalize()}")
        return res

    def unlink(self):
        for rec in self:
            rec._log_change_on_employee(f"❌ Leave entry removed: {rec.date} – {rec.leave_type.capitalize()}")
        return super().unlink()