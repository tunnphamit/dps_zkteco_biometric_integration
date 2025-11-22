# -*- coding: utf-8 -*-
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2024 DOTSPRIME SYSTEM LLP
#    Email : sales@dotsprime.com / dotsprime@gmail.com
########################################################

import base64
import unicodedata
from odoo import api, fields, models, _
from collections import defaultdict
from odoo.addons.base.models.res_partner import _tz_get
import pytz
from datetime import datetime
from ..zk import ZK
from odoo.exceptions import UserError, ValidationError
import re


class ZktecoDeviceSetting(models.Model):
    """
    ZKTeco Device Configuration Model

    This model stores configuration details for ZKTeco biometric devices including
    connection settings, user assignments, attendance logs, operational parameters,
    and device state tracking.

    Fields:
        name: Name of the device configuration.
        zkteco_device_ip_address: IP address of the device.
        port: Connection port.
        password_configured: Boolean flag if the device password is set.
        zkteco_device_pass: Device password (optional).
        time_zone: Device timezone.
        company_id: Company linked to the device.
        delay: Standard polling delay for device data.
        error_delay: Delay used for error handling.
        zkteco_device_real_time: Enable real-time data fetching.
        device_t_interval: Interval between transactions fetched from the device.
        is_adms: Flag for ADMS-enabled devices.
        serial_number: Device serial number.
        zkteco_device_user_ids: Users mapped to the device.
        device_operation_stamplogs: Operation stamp logs.
        device_stamp_logs: Stamp logs.
        device_attendance_logs_no: Computed number of attendance logs.
        device_command_no_count: Computed number of device commands.
        state: Device connection state.
        zkteco_attendance_device_status_ids: Attendance state records for the device.
    """

    _name = 'zkteco.device.setting'
    _description = 'ZKTeco Device Setting Configuration'

    name = fields.Char(
        string='Name',
        required=True,
        help='Enter a descriptive name for the ZKTeco device.',
        tracking=True
    )
    zkteco_device_ip_address = fields.Char(
        string='Device IP',
        help='IP address used to connect to the ZKTeco device.',
        tracking=True
    )
    port = fields.Integer(
        string='Port',
        help='Network port used for connecting to the device.',
        tracking=True
    )
    password_configured = fields.Boolean(
        string='Is Password Set',
        default=False,
        help='Indicates if a password has been configured for the device.',
        tracking=True
    )
    zkteco_device_pass = fields.Char(
        string='Device Password',
        null=True,
        blank=True,
        help='Password required to connect to the device if configured.',
        tracking=False
    )

    time_zone = fields.Selection(
        _tz_get,
        string='Timezone',
        default=lambda self: self.env.user.tz or 'GMT',
        help='Timezone of the device for attendance logging.',
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        help='Company this device is linked to.',
        tracking=True
    )
    delay = fields.Integer(
        string="Delay",
        default=10,
        help='Delay interval (in seconds) for polling the device.',
        tracking=True
    )
    error_delay = fields.Integer(
        string="Error Delay",
        default=30,
        help='Delay interval (in seconds) when device errors occur.',
        tracking=True
    )
    zkteco_device_real_time = fields.Boolean(
        string="Real Time",
        help='Enable real-time attendance capture from the device.',
        tracking=True
    )
    device_t_interval = fields.Integer(
        string="Transaction Interval",
        default=2,
        help='Interval between transactions fetched from the device.',
        tracking=True
    )
    is_adms = fields.Boolean(
        string='ADMS',
        help='Indicates whether the device supports ADMS.',
        tracking=True
    )
    serial_number = fields.Char(
        string='Serial Number',
        help='Device serial number for identification.',
        tracking=True
    )

    zkteco_device_user_ids = fields.One2many(
        'zkteco.attendance.machine', 'device_id', string='Users',
        help='List of users registered on the device.'
    )
    device_operation_stamplogs = fields.One2many(
        'device.operation.stamplogs', 'device_id', string='Operation Stamp Logs',
        help='Operational stamp logs retrieved from the device.'
    )
    device_stamp_logs = fields.One2many(
        'device.stamp.logs', 'device_id', string='Stamp Log',
        help='Attendance stamp logs recorded by the device.'
    )

    device_attendance_logs_no = fields.Integer(
        string='Attendance Logs',
        compute='_compute_attendance_log_count',
        help='Total number of attendance logs captured by the device.',
        tracking=True
    )
    device_command_no_count = fields.Integer(
        string='Command Count',
        compute='_compute_device_no_count',
        help='Number of commands sent to the device.',
        tracking=True
    )

    state = fields.Selection(
        [('not_connected', 'Not Connected'), ('connected', 'Connected')],
        default='not_connected',
        help='Connection status of the device.',
        tracking=True
    )

    zkteco_attendance_device_status_ids = fields.One2many(
        'zkteco.device.states', 'device_id', string="Attendance States",
        help='Attendance state logs for the device.'
    )


    @api.onchange('password_configured')
    def onchange_password_configured(self):

        if not self.password_configured:
            self.zkteco_device_pass = ''


    @api.constrains('is_adms')
    def _constraint_adms_setting(self):

        default_states = [
            (0, 0, {'name': 'Check-In', 'code': 1, 'activity_type': 'check_in'}),
            (0, 0, {'name': 'Check-Out', 'code': 2, 'activity_type': 'check_out'}),
        ]
        if self.is_adms and not self.zkteco_attendance_device_status_ids:
            self.zkteco_attendance_device_status_ids = default_states


    @api.onchange('zkteco_device_pass')
    def _onchange_zkteco_device_password(self):

        password_value = self.zkteco_device_pass or ''
        if password_value and not password_value.isdigit():
            raise UserError(
                _("Invalid Device Password: The password must contain only numeric characters.")
            )

    def action_validate_zkteco_connection(self):

        device_ip = self.zkteco_device_ip_address
        device_port = self.port
        device_password = self.zkteco_device_pass

        zk_device = ZK(device_ip, device_port, password=device_password)

        try:
            connection_result = zk_device.connect()
            if connection_result:
                raise UserError(_("ZKTeco Device connection established successfully."))
            else:
                raise ValidationError(_("Failed to establish connection with the ZKTeco device."))
        except Exception as connection_exception:
            raise UserError(_(
                f"An unexpected error occurred while connecting to the device: {connection_exception}"
            ))

    # Customized by Tunn
    # Function to remove accents + remove spaces (prepare username for ZKTeco)
    def _clean_username(self, text):
        """
        Convert Vietnamese accented text into ASCII (no accents) and remove spaces.
        """
        if not text:
            return ''

        # Remove accents
        text = unicodedata.normalize('NFKD', text)
        text = ''.join([c for c in text if not unicodedata.combining(c)])

        # Normalize spaces (remove multiple spaces)
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)

        # Lower-case first, then capitalize each word
        text = text.lower().title()

        # Remove all spaces between words
        text = text.replace(' ', '')

        return text

    def action_synchronize_employees(self):

        max_uid = 0
        next_user_id_str = '1'
        uid_list = []
        device_user_id_list = []

        all_employees = self.env['hr.employee'].search([])

        device_ip = self.zkteco_device_ip_address
        device_port = self.port
        device_password = self.zkteco_device_pass

        zk_device = ZK(device_ip, device_port, password=device_password)

        try:
            connection_result = zk_device.connect()
            if not connection_result:
                raise ValidationError(_("Failed to establish connection with the ZKTeco device."))

            existing_users = zk_device.get_users()
            print("USERS", existing_users)

            def generate_next_user_id(current_user_id):

                pattern = r'(\d+)'

                def increment(match):
                    number = match.group(0)
                    incremented_number = str(int(number) + 1)
                    return incremented_number

                return re.sub(pattern, increment, current_user_id)

            if existing_users:
                for user in existing_users:
                    uid_list.append(user.uid)
                    device_user_id_list.append(user.user_id)

                uid_list.sort()
                device_user_id_list.sort()
                max_uid = uid_list[-1]
                next_user_id_str = str(generate_next_user_id(device_user_id_list[-1]))

                attempt_counter = 2
                while True:
                    if next_user_id_str in device_user_id_list:
                        next_user_id_str = str(generate_next_user_id(device_user_id_list[-1 * attempt_counter]))
                        attempt_counter += 1
                    else:
                        for emp_index in range(len(all_employees)):
                            test_user_id = generate_next_user_id(next_user_id_str)
                            if test_user_id in device_user_id_list:
                                next_user_id_str = test_user_id
                                continue
                        break

            for employee in all_employees:
                biometric_device_record = employee.biometric_device_ids.search([
                    ('employee_id', '=', employee.id),
                    ('device_id', '=', self.id)
                ])

                if not biometric_device_record:
                    max_uid += 1
                    employee.biometric_device_ids = [(0, 0, {
                        'employee_id': employee.id,
                        'zkteco_device_attend_id': next_user_id_str,
                        'device_id': self.id,
                    })]

                    # Customized By Tunn
                    clean_name = self._clean_username(employee.name)
                    zk_device.set_user(
                        max_uid,
                        clean_name,
                        0,
                        '',
                        '',
                        str(next_user_id_str)
                    )

                    next_user_id_str = generate_next_user_id(next_user_id_str)

            return {
                'name': 'Success Message',
                'type': 'ir.actions.act_window',
                'res_model': 'employee.sync.wizard',
                'view_mode': 'form',
                'view_type': 'form',
                'target': 'new'
            }

        except Exception as sync_exception:
            raise UserError(_(
                f"An unexpected error occurred during employee synchronization: {sync_exception}"
            ))

    def action_pull_attendance_logs(self):

        attendance_model = self.env['zkteco.device.logs']

        device_ip = self.zkteco_device_ip_address
        device_port = self.port
        device_password = self.zkteco_device_pass
        zk = ZK(device_ip, device_port, password=device_password)

        try:
            connection = zk.connect()
            if connection:
                raw_attendance_records = zk.get_attendance()
                print("Retrieved attendance records:", raw_attendance_records)
                device_name = self.name
                company = self.company_id

                if raw_attendance_records:
                    processed_attendance_list = []

                    for record in raw_attendance_records:
                        attendance_time = record.timestamp
                        attendance_time = datetime.strptime(
                            attendance_time.strftime('%Y-%m-%d %H:%M:%S'),
                            '%Y-%m-%d %H:%M:%S'
                        )
                        local_tz = pytz.timezone(self.time_zone or 'GMT')
                        local_dt = local_tz.localize(attendance_time, is_dst=None)
                        utc_dt = local_dt.astimezone(pytz.utc)
                        utc_str = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
                        attendance_time_utc = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
                        attendance_time_utc = fields.Datetime.to_string(attendance_time_utc)

                        employee_records = self.env['zkteco.attendance.machine'].search([
                            ('zkteco_device_attend_id', '=', record.user_id),
                            ('device_id', '=', self.id)
                        ])

                        if len(employee_records) > 1:
                            employee_names = employee_records.mapped('employee_id.name')
                            raise UserError(_(
                                f"Duplicate Biometric User ID detected for employees: {', '.join(employee_names)}"
                            ))

                        if employee_records:
                            attendance_dict = {
                                'user_id': record.user_id,
                                'attendance_time': attendance_time_utc,
                                'employee_id': employee_records.employee_id.id
                            }
                            processed_attendance_list.append(attendance_dict)

                    employee_status_tracker = defaultdict(list)
                    sorted_attendance = sorted(processed_attendance_list,
                                               key=lambda x: (x['user_id'], x['attendance_time']))

                    for entry in sorted_attendance:
                        user_id = entry['user_id']
                        employee_id = entry['employee_id']
                        entry_time_str = entry['attendance_time']
                        entry_time_dt = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')

                        if not employee_status_tracker[user_id]:
                            status = 'Check-in'
                        else:
                            previous_status = employee_status_tracker[user_id][-1]['status']
                            status = 'Check-out' if previous_status == 'Check-in' else 'Check-in'

                        employee_status_tracker[user_id].append({
                            'status': status,
                            'time': entry_time_dt,
                            'employee_id': employee_id,
                            'entry_time': entry_time_str
                        })
                        entry['status'] = status

                        existing_log = attendance_model.search([
                            ('employee_id', '=', employee_id),
                            ('user_punch_time', '=', entry_time_str)
                        ])

                        attendance_status_value = '0' if status == 'Check-in' else '1'
                        vals = {
                            'employee_id': employee_id,
                            'user_punch_time': entry_time_dt if not existing_log or not existing_log.user_punch_calculated else entry_time_str,
                            'status': attendance_status_value,
                            'device': str(device_name),
                            'company_id': company.id,
                            'user_punch_calculated': bool(existing_log and existing_log.user_punch_calculated)
                        }

                        if existing_log:
                            existing_log.write(vals)
                        else:
                            attendance_model.create(vals)

                    return {
                        'name': 'Attendance Pull Success',
                        'type': 'ir.actions.act_window',
                        'res_model': 'zkteco_success',
                        'view_mode': 'form',
                        'view_type': 'form',
                        'target': 'new'
                    }
                else:
                    raise UserError(_("No attendance records found on the device."))

            else:
                raise ValidationError(_("Unable to connect to the device. Please check the IP, port, and password."))

        except Exception as exc:
            raise UserError(_(f"An error occurred while fetching attendance logs: {str(exc)}"))

    def action_pull_attendance_logs_new(self):

        zkteco_devices = self.env["zkteco.device.setting"].search([])

        for zkteco_device in zkteco_devices:
            try:
                if zkteco_device.is_adms:
                    zkteco_device.action_pull_attendance_logs()
            except UserError as ue:
                raise UserError(
                    _(f"Failed to fetch attendance logs for device '{zkteco_device.name}': {ue}")
                )
            except Exception as ex:
                raise UserError(
                    _(f"An unexpected error occurred while fetching logs for device '{zkteco_device.name}': {ex}")
                )


    def _compute_attendance_log_count(self):

        for zkteco_device in self:
            zkteco_device.device_attendance_logs_no = self.env[
                'zkteco.device.event.log'
            ].search_count([
                ('device_id', '=', zkteco_device.id)
            ])

    def _compute_device_no_count(self):

        for zkteco_device in self:
            zkteco_device.device_command_no_count = self.env[
                'zkteco.dcmmand'
            ].search_count([
                ('device_id', '=', zkteco_device.id)
            ])

    def action_view_zkteco_attendance_logs(self):

        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Attendance Data Logs',
            'view_mode': 'list,form',
            'res_model': 'zkteco.device.event.log',
            'domain': [('device_id', '=', self.id)],
            'context': dict(self.env.context, default_device_id=self.id),
        }

    def action_device_fingerprint_open(self):

        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Fingerprint Templates',
            'view_mode': 'list,form',
            'res_model': 'zkteco.device.fingerprints',
            'domain': [('device_id', '=', self.id)],  # Filter templates by current device
            'context': dict(self.env.context, default_device_id=self.id),
        }


    def action_open_zkteco_device_commands(self):

        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Command To Device',
            'view_mode': 'list,form',
            'res_model': 'zkteco.dcmmand',
            'domain': [('device_id', '=', self.id)],
            'context': dict(self.env.context, default_device_id=self.id),
        }

    def create_oplog(self, log_values, op_stamp):

        combined_datetime = datetime.strptime(f"{log_values[3]} {log_values[4]}", "%Y-%m-%d %H:%M:%S")

        local_timezone = pytz.timezone('Asia/Kolkata')
        localized_datetime = local_timezone.localize(combined_datetime)

        utc_datetime = localized_datetime.astimezone(pytz.utc)
        formatted_utc_datetime = utc_datetime.strftime('%Y-%m-%d %H:%M:%S')

        self.env['zkteco.device.event.log'].sudo().create({
            'device_id': self.id,
            'log_code': log_values[1],
            'description': log_values[1],
            'operator': log_values[2],
            'op_time': formatted_utc_datetime,
            'value_1': log_values[5],
            'value_2': log_values[6],
            'value_3': log_values[7],
            'reserved': log_values[8],
            'opStamp': op_stamp,
        })

    def action_create_employee_device_user(self, raw_values):

        device_user_id = raw_values[1].split('=')[1]
        device_user_name = raw_values[2].split('=')[1]

        existing_employee = self.env['zkteco.attendance.machine'].sudo().search([
            ('zkteco_device_attend_id', '=', device_user_id)
        ])

        if existing_employee:
            existing_employee.zkteco_device_username = device_user_name
            employee_record = existing_employee
        else:
            employee_record = self.env['zkteco.attendance.machine'].sudo().create({
                'zkteco_device_attend_id': device_user_id,
                'device_id': self.id,
                'zkteco_device_username': device_user_name,
            })

        return employee_record

    def action_create_device_zkteco_logs(self, raw_data):

        for record_line in raw_data.splitlines():
            line_values = record_line.split()
            device_user_id = line_values[0]
            punch_date = line_values[1]
            punch_time = line_values[2]
            punch_number = line_values[3]
            punch_status_code = int(line_values[4])

            # Customized by Tunn
            # device_user_record = self.env['zkteco.attendance.machine'].sudo().search([
            #     ('zkteco_device_attend_id', '=', device_user_id)
            # ])
            device_user_record = self.env['zkteco.attendance.machine'].sudo().search([
                ('zkteco_device_attend_id', '=', device_user_id),
                ('device_id', '=', self.id)
            ], limit=1)

            if not device_user_record:
                device_user_record = self.env['zkteco.attendance.machine'].sudo().create({
                    'zkteco_device_attend_id': device_user_id,
                    'device_id': self.id
                })

            local_datetime = datetime.strptime(f"{punch_date} {punch_time}", "%Y-%m-%d %H:%M:%S")
            local_tz = pytz.timezone(self.time_zone)
            localized_datetime = local_tz.localize(local_datetime)
            utc_datetime = localized_datetime.astimezone(pytz.utc)
            timestamp = local_datetime.timestamp()
            formatted_utc_datetime = utc_datetime.strftime('%Y-%m-%d %H:%M:%S')

            # Customized by Tunn
            # existing_log = self.env['zkteco.device.logs'].sudo().search([
            #     ('zketco_duser_id', '=', device_user_record.id),
            #     ('timestamp', '=', timestamp)
            # ])
            existing_log = self.env['zkteco.device.logs'].sudo().search([
                ('zketco_duser_id', '=', device_user_record.id),
                ('timestamp', '=', timestamp)
            ], limit=1)

            state_record = self.env['zkteco.device.states'].search([
                ('code', '=', punch_status_code),
                ('device_id', '=', self.id)
            ], limit=1)

            if state_record:
                if state_record.activity_type == 'check_in':
                    punch_status = '0'
                elif state_record.activity_type == 'check_out':
                    punch_status = '1'
                else:
                    punch_status = '2'
            else:
                punch_status = '2'

            if not existing_log:
                self.env['zkteco.device.logs'].sudo().create({
                    'zketco_duser_id': device_user_record.id,
                    'company_id': self.company_id.id,
                    'user_punch_time': formatted_utc_datetime,
                    'status_number': punch_status_code,
                    'number': punch_number,
                    'status': punch_status,
                    'device': self.name,
                    'timestamp': timestamp,
                })

    def action_create_device_user_fingerprint(self, values):


        user_device_id = values[1].split('=')[1]
        fingerprint_template = values[5].split('=')[1]

        fixed_template = self._base64_fix_padding(fingerprint_template)
        
        # Customized by Tunn
        # db_user_device = self.env['zkteco.attendance.machine'].sudo().search(
        #     [('zkteco_device_attend_id', '=', user_device_id)]
        # )
        db_user_device = self.env['zkteco.attendance.machine'].sudo().search([
            ('zkteco_device_attend_id', '=', user_device_id),
            ('device_id', '=', self.id)
        ], limit=1)


        if not db_user_device:
            db_user_device = self.env['zkteco.attendance.machine'].sudo().create({
                'zkteco_device_attend_id': user_device_id,
                'device_id': self.id
            })

        existing_fp = self.env['zkteco.device.fingerprints'].sudo().search([
            ('device_id', '=', self.id),
            ('zketco_duser_id', '=', db_user_device.id)
        ])

        if existing_fp:
            existing_fp.template_data = fixed_template
        else:
            self.env['zkteco.device.fingerprints'].sudo().create({
                'zketco_duser_id': db_user_device.id,
                'device_id': self.id,
                'template_data': fixed_template
            })
########################################################################################################################

    def _base64_fix_padding(self, encoded_string):

        padding_needed = len(encoded_string) % 4
        if padding_needed:
            encoded_string += '=' * (4 - padding_needed)
        decoded_data = base64.b64decode(encoded_string)
        return base64.b64encode(decoded_data)

    def action_create_zkteco_device_user_commands(self):

        pending_commands = self.env['zkteco.dcmmand'].sudo().search([
            ('status', '=', 'pending'),
            ('device_id', '=', self.id)
        ])
        combined_log = ""
        for cmd in pending_commands:
            combined_log += cmd.execution_log
            cmd.status = 'executed'
        return combined_log

    def action_check_zkteco_device_command_revert_res(self, command_record_id):

        if not command_record_id:
            return

        command_record = self.env['zkteco.dcmmand'].search([('id', '=', command_record_id)])
        if not command_record:
            return

        if command_record.employee_id and command_record.name == "DATA":
            log_values = command_record.execution_log.split()
            device_user_id = log_values[2].split('=')[1]
            device_user_name = log_values[3].split('=')[1]

            device_user = self.env['zkteco.attendance.machine'].sudo().search([
                ('zkteco_device_attend_id', '=', device_user_id),
                ('device_id', '=', self.id)
            ])

            if not device_user:
                device_user = self.env['zkteco.attendance.machine'].sudo().create({
                    'zkteco_device_attend_id': device_user_id,
                    'device_id': self.id,
                    'zkteco_device_username': device_user_name,
                    'employee_id': command_record.employee_id.id
                })
            else:
                device_user.employee_id = command_record.employee_id
                device_user.zkteco_device_username = command_record.employee_id.name

            command_record.status = 'success'

        elif command_record.employee_id and command_record.name == "DEL":
            log_values = command_record.execution_log.split()
            device_user_id = log_values[2].split('=')[1]

            device_user = self.env['zkteco.attendance.machine'].sudo().search([
                ('zkteco_device_attend_id', '=', device_user_id),
                ('device_id', '=', self.id)
            ])
            device_user.unlink()
            command_record.status = 'success'

        elif command_record.employee_id and command_record.name == "UPDATE":
            device_user = self.env['zkteco.attendance.machine'].sudo().search([
                ('zkteco_device_attend_id', '=', command_record.pin),
                ('device_id', '=', self.id)
            ])
            device_user.zkteco_device_username = command_record.employee_id.name
            command_record.status = 'success'

        elif command_record.name in ["USERINFO", "CHECK"]:
            command_record.status = 'success'

        return command_record

    def action_export_device_employee(self):

        employees_to_export = self.env['hr.employee'].search([
            ('biometric_device_ids', '=', False)
        ])
        for employee in employees_to_export:
            employee.create_export_command(self)

    def action_zkteco_device_user_data_download(self):

        pending_userinfo_cmd = self.env['zkteco.dcmmand'].sudo().search([
            ('device_id', '=', self.id),
            ('name', '=', 'USERINFO'),
            ('status', '=', 'pending')
        ])

        if not pending_userinfo_cmd:
            pending_userinfo_cmd = self.env['zkteco.dcmmand'].sudo().create({
                'name': 'USERINFO',
                'device_id': self.id,
                'status': 'pending'
            })
            pending_userinfo_cmd.execution_log = f"C:{pending_userinfo_cmd.id}:DATA QUERY USERINFO\n"

    def action_check_device_connection(self):

        pending_check_cmd = self.env['zkteco.dcmmand'].sudo().search([
            ('device_id', '=', self.id),
            ('name', '=', 'CHECK'),
            ('status', '=', 'pending')
        ])

        if not pending_check_cmd:
            pending_check_cmd = self.env['zkteco.dcmmand'].sudo().create({
                'name': 'CHECK',
                'device_id': self.id,
                'status': 'pending',
            })
            pending_check_cmd.execution_log = f"C:{pending_check_cmd.id}:CHECK\n"

    def action_sync_employees_all_devices(self):


        all_employees = self.env['hr.employee'].search([])
        all_devices = self.search([])

        for employee in all_employees:
            for device in all_devices:

                existing_record = self.env['zkteco.attendance.machine'].search([
                    ('employee_id', '=', employee.id),
                    ('device_id', '=', device.id),
                ])

                try:
                    if not existing_record:
                        if device.is_adms:
                            employee.create_export_command(device)
                        else:
                            device_user_id = ''
                            for line in employee.biometric_device_ids:
                                device_user_id = line.zkteco_device_attend_id

                            ip_address = device.zkteco_device_ip_address
                            port_number = device.port
                            device_password = device.zkteco_device_pass

                            zk_connection = ZK(ip_address, port_number, password=device_password)
                            connection = zk_connection.connect()

                            if connection:
                                device_users = zk_connection.get_users()

                                already_exists = any(
                                    user.user_id == device_user_id for user in device_users
                                )

                                if already_exists:
                                    continue
                                else:
                                    if device_user_id:
                                        zk_connection.set_user(
                                            int(device_user_id),
                                            employee.name,
                                            0,  # Privilege
                                            '', '',  # Empty password and card number
                                            device_user_id
                                        )
                                    else:
                                        employee.update_zkteco_device_emp()

                                zk_connection.disconnect()
                            else:
                                raise ValidationError(
                                    f"Failed to establish connection with the device {device.name} at {ip_address}:{port_number}."
                                )
                except Exception:
                    continue


