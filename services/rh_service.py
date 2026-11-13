"""HR-only employee records and schedule access."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import ConfiguracaoJornada, RegistroPonto, Usuario
from services.auth_service import assert_user_role, get_active_user
from services.ponto_service import effective_punch_times, list_punches


def get_hr_overview(
    session: Session, actor_id: int
) -> tuple[list[Usuario], list[dict], list[dict]]:
    actor = get_active_user(session, actor_id)
    assert_user_role(actor, ("rh", "admin"))

    employees = list(
        session.scalars(
            select(Usuario)
            .where(Usuario.perfil == "funcionario")
            .order_by(Usuario.nome, Usuario.id)
        )
    )
    employee_ids = [employee.id for employee in employees]
    schedules = {}
    if employee_ids:
        schedules = {
            schedule.usuario_id: schedule
            for schedule in session.scalars(
                select(ConfiguracaoJornada).where(
                    ConfiguracaoJornada.usuario_id.in_(employee_ids)
                )
            )
        }

    schedule_rows = []
    punch_rows = []
    for employee in employees:
        schedule = schedules.get(employee.id)
        schedule_rows.append(
            {
                "Funcionário": employee.nome,
                "E-mail": employee.email,
                "Ativo": "Sim" if employee.ativo else "Não",
                "Horas diárias": float(schedule.horas_diarias_referencia) if schedule else 8.0,
                "Horas semanais": float(schedule.horas_semanais_referencia) if schedule else 48.0,
                "Entrada prevista": (
                    schedule.horario_entrada_preferencial.strftime("%H:%M")
                    if schedule and schedule.horario_entrada_preferencial
                    else "—"
                ),
                "Saída prevista": (
                    schedule.horario_saida_preferencial.strftime("%H:%M")
                    if schedule and schedule.horario_saida_preferencial
                    else "—"
                ),
                "Intervalos": schedule.quantidade_intervalos if schedule else 1,
                "Fuso horário": schedule.fuso_horario if schedule else "America/Sao_Paulo",
            }
        )
        punches = list_punches(session, employee.id)
        times = effective_punch_times(session, employee.id, punches)
        for punch in punches:
            punch_rows.append(
                {
                    "Funcionário": employee.nome,
                    "E-mail": employee.email,
                    "Data efetiva": times[punch.id].strftime("%d/%m/%Y"),
                    "Horário efetivo": times[punch.id].strftime("%H:%M:%S"),
                    "Tipo": punch.tipo_registro.replace("_", " ").title(),
                    "Origem": punch.origem,
                }
            )
    return employees, schedule_rows, punch_rows