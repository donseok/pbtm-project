forward
global type u_steel_common from userobject
end type
end forward

global type u_steel_common from userobject
end type

public function string f_get_user_id();
  // 현재 로그인 사용자 ID 반환
  string ls_user_id
  SELECT user_id INTO :ls_user_id
    FROM tb_session
   WHERE session_id = gs_session_id;
  if SQLCA.SQLCode <> 0 then ls_user_id = "SYSTEM"
  return ls_user_id
end function

public function string f_get_plant_name(string as_plant_cd);
  // 공장명 조회
  string ls_plant_nm
  SELECT plant_nm INTO :ls_plant_nm
    FROM tb_plant
   WHERE plant_cd = :as_plant_cd;
  if SQLCA.SQLCode <> 0 then ls_plant_nm = "Unknown"
  return ls_plant_nm
end function

public function integer f_log_action(string as_action, string as_detail);
  // 사용자 행위 로그 기록
  INSERT INTO tb_action_log (user_id, action_cd, detail, log_dt)
  VALUES (f_get_user_id(), :as_action, :as_detail, getdate());
  commit;
  return 1
end function

public function decimal f_convert_unit(decimal ad_value, string as_from_unit, string as_to_unit);
  // 단위 변환 (ton <-> kg)
  decimal ld_factor
  SELECT convert_factor INTO :ld_factor
    FROM tb_unit_convert
   WHERE from_unit = :as_from_unit
     AND to_unit   = :as_to_unit;
  if SQLCA.SQLCode <> 0 then ld_factor = 1
  return ad_value * ld_factor
end function
