forward
global type w_quality_inspect from window
end type
end forward

global type w_quality_inspect from window
integer width = 3400
integer height = 2600
string title = "품질검사 실적"
end type

on w_quality_inspect.create
  call super::create
  trigger event constructor()
end on

event constructor();
  // 품질검사 화면 초기화
  f_init_inspect_items()
  dw_quality_result.SetTransObject(SQLCA)
end event

event open();
  string ls_lot_no
  ls_lot_no = message.stringparm

  if IsNull(ls_lot_no) or ls_lot_no = "" then
    // LOT번호 없으면 전체 미검사 목록 조회
    dw_quality_result.retrieve("PENDING")
  else
    sle_lot_no.text = ls_lot_no
    dw_quality_result.retrieve(ls_lot_no)
  end if

  f_update_inspect_status()
end event

event clicked();
  // 검사 항목 선택
  long ll_row
  ll_row = dw_quality_result.GetClickedRow()

  if ll_row > 0 then
    string ls_inspect_cd
    ls_inspect_cd = dw_quality_result.GetItemString(ll_row, "inspect_cd")
    f_show_inspect_detail(ls_inspect_cd)
  end if
end event

event ue_save_inspect();
  // 품질검사 결과 저장
  long ll_row_count, ll_idx
  string ls_lot_no, ls_inspect_cd, ls_result, ls_judge
  decimal ld_value_1, ld_value_2, ld_value_3
  string ls_inspector_id, ls_remark

  ll_row_count = dw_quality_result.RowCount()

  for ll_idx = 1 to ll_row_count
    if dw_quality_result.GetItemStatus(ll_idx, 0, Primary!) = DataModified! then
      ls_lot_no      = dw_quality_result.GetItemString(ll_idx, "lot_no")
      ls_inspect_cd  = dw_quality_result.GetItemString(ll_idx, "inspect_cd")
      ld_value_1     = dw_quality_result.GetItemDecimal(ll_idx, "measure_val_1")
      ld_value_2     = dw_quality_result.GetItemDecimal(ll_idx, "measure_val_2")
      ld_value_3     = dw_quality_result.GetItemDecimal(ll_idx, "measure_val_3")
      ls_inspector_id = dw_quality_result.GetItemString(ll_idx, "inspector_id")
      ls_remark      = dw_quality_result.GetItemString(ll_idx, "remark")

      // 판정 로직 호출
      ls_judge = f_judge_quality(ls_inspect_cd, ld_value_1, ld_value_2, ld_value_3)
      ls_result = ls_judge

      UPDATE tb_quality_result
         SET measure_val_1 = :ld_value_1,
             measure_val_2 = :ld_value_2,
             measure_val_3 = :ld_value_3,
             inspect_result = :ls_result,
             judge_cd       = :ls_judge,
             inspector_id   = :ls_inspector_id,
             inspect_dt     = getdate(),
             remark         = :ls_remark
       WHERE lot_no = :ls_lot_no
         AND inspect_cd = :ls_inspect_cd;

      if SQLCA.SQLCode <> 0 then
        messagebox("오류", "검사결과 저장 실패: " + SQLCA.SQLErrText)
        rollback;
        return
      end if

      // 검사이력 테이블에 기록
      INSERT INTO tb_quality_hist
        (lot_no, inspect_cd, measure_val_1, measure_val_2, measure_val_3,
         judge_cd, inspector_id, inspect_dt, remark)
      VALUES
        (:ls_lot_no, :ls_inspect_cd, :ld_value_1, :ld_value_2, :ld_value_3,
         :ls_judge, :ls_inspector_id, getdate(), :ls_remark);

    end if
  next

  // 전체 LOT 판정 갱신
  ls_lot_no = sle_lot_no.text
  f_update_lot_judge(ls_lot_no)

  commit;
  messagebox("확인", "검사결과가 저장되었습니다.")
  trigger event open()
end event

event ue_create_inspect();
  // 신규 검사 항목 일괄 생성
  string ls_lot_no, ls_prod_cd
  ls_lot_no = sle_lot_no.text

  if ls_lot_no = "" then
    messagebox("알림", "LOT번호를 입력하세요.")
    return
  end if

  // 제품코드로 검사항목 조회 후 일괄 생성
  SELECT prod_cd INTO :ls_prod_cd
    FROM tb_prod_result
   WHERE lot_no = :ls_lot_no;

  INSERT INTO tb_quality_result (lot_no, inspect_cd, inspect_nm, spec_min, spec_max, status, create_dt)
  SELECT :ls_lot_no, qi.inspect_cd, qi.inspect_nm, qi.spec_min, qi.spec_max, 'PENDING', getdate()
    FROM tb_quality_inspect_master qi
   WHERE qi.prod_cd = :ls_prod_cd
     AND qi.use_yn = 'Y';

  if SQLCA.SQLCode <> 0 then
    messagebox("오류", "검사항목 생성 실패: " + SQLCA.SQLErrText)
    rollback;
    return
  end if

  commit;
  dw_quality_result.retrieve(ls_lot_no)
end event

event ue_open_prod();
  // 생산실적 화면으로 이동
  string ls_lot_no
  ls_lot_no = sle_lot_no.text
  if ls_lot_no <> "" then
    openwithparm(w_prod_result, ls_lot_no)
  end if
end event

event ue_hold();
  // 품질 보류 처리
  long ll_row
  string ls_lot_no

  ll_row = dw_quality_result.GetRow()
  if ll_row <= 0 then return

  ls_lot_no = dw_quality_result.GetItemString(ll_row, "lot_no")

  UPDATE tb_inventory
     SET inv_status = 'HOLD',
         update_dt  = getdate()
   WHERE lot_no = :ls_lot_no;

  UPDATE tb_prod_result
     SET status    = 'HOLD',
         update_dt = getdate()
   WHERE lot_no = :ls_lot_no;

  commit;
  messagebox("확인", "해당 LOT이 보류 처리되었습니다.")
end event

public function integer f_init_inspect_items();
  // 검사 항목 콤보 초기화
  ddlb_judge.AddItem("PASS")
  ddlb_judge.AddItem("FAIL")
  ddlb_judge.AddItem("HOLD")
  ddlb_judge.AddItem("RETEST")
  return 1
end function

public function string f_judge_quality(string as_inspect_cd, decimal ad_val1, decimal ad_val2, decimal ad_val3);
  // 스펙 대비 합격/불합격 자동 판정
  decimal ld_spec_min, ld_spec_max

  SELECT spec_min, spec_max
    INTO :ld_spec_min, :ld_spec_max
    FROM tb_quality_inspect_master
   WHERE inspect_cd = :as_inspect_cd;

  if ad_val1 >= ld_spec_min and ad_val1 <= ld_spec_max then
    return "PASS"
  else
    return "FAIL"
  end if
end function

public function integer f_update_inspect_status();
  // 검사 진행률 표시
  long ll_total, ll_done

  SELECT count(*) INTO :ll_total
    FROM tb_quality_result
   WHERE lot_no = sle_lot_no.text;

  SELECT count(*) INTO :ll_done
    FROM tb_quality_result
   WHERE lot_no = sle_lot_no.text
     AND status <> 'PENDING';

  st_progress.text = "검사 진행: " + string(ll_done) + " / " + string(ll_total)
  return 1
end function

public function integer f_update_lot_judge(string as_lot_no);
  // LOT 전체 판정 결과 갱신
  long ll_fail_count

  SELECT count(*) INTO :ll_fail_count
    FROM tb_quality_result
   WHERE lot_no = :as_lot_no
     AND judge_cd = 'FAIL';

  if ll_fail_count > 0 then
    UPDATE tb_prod_result SET status = 'QC_FAIL', update_dt = getdate() WHERE lot_no = :as_lot_no;
  else
    UPDATE tb_prod_result SET status = 'QC_PASS', update_dt = getdate() WHERE lot_no = :as_lot_no;
  end if

  return 1
end function

public function integer f_show_inspect_detail(string as_inspect_cd);
  // 검사 항목 상세 팝업
  messagebox("검사 상세", "검사코드: " + as_inspect_cd)
  return 1
end function
