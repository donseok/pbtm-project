forward
global type w_prod_result from window
end type
end forward

global type w_prod_result from window
integer width = 3200
integer height = 2400
string title = "생산실적 등록/조회"
end type

on w_prod_result.create
  call super::create
  trigger event constructor()
end on

event constructor();
  // 생산실적 화면 초기화
  f_init_screen()
  dw_prod_result.SetTransObject(SQLCA)
end event

event open();
  string ls_plant_cd
  ls_plant_cd = message.stringparm

  if IsNull(ls_plant_cd) or ls_plant_cd = "" then
    ls_plant_cd = f_get_default_plant()
  end if

  dw_prod_result.retrieve(ls_plant_cd, today())
  f_set_title("생산실적 - " + ls_plant_cd)
end event

event clicked();
  // 행 선택 시 품질검사 화면 호출
  long ll_row
  ll_row = dw_prod_result.GetClickedRow()

  if ll_row > 0 then
    string ls_lot_no
    ls_lot_no = dw_prod_result.GetItemString(ll_row, "lot_no")
    openwithparm(w_quality_inspect, ls_lot_no)
  end if
end event

event ue_save();
  // 생산실적 저장
  long ll_row_count, ll_idx
  string ls_lot_no, ls_prod_cd, ls_line_cd
  decimal ld_qty, ld_weight
  string ls_shift, ls_worker_id

  ll_row_count = dw_prod_result.RowCount()

  for ll_idx = 1 to ll_row_count
    if dw_prod_result.GetItemStatus(ll_idx, 0, Primary!) = DataModified! then
      ls_lot_no   = dw_prod_result.GetItemString(ll_idx, "lot_no")
      ls_prod_cd  = dw_prod_result.GetItemString(ll_idx, "prod_cd")
      ls_line_cd  = dw_prod_result.GetItemString(ll_idx, "line_cd")
      ld_qty      = dw_prod_result.GetItemDecimal(ll_idx, "prod_qty")
      ld_weight   = dw_prod_result.GetItemDecimal(ll_idx, "prod_weight")
      ls_shift    = dw_prod_result.GetItemString(ll_idx, "shift_cd")
      ls_worker_id = dw_prod_result.GetItemString(ll_idx, "worker_id")

      UPDATE tb_prod_result
         SET prod_cd     = :ls_prod_cd,
             line_cd     = :ls_line_cd,
             prod_qty    = :ld_qty,
             prod_weight = :ld_weight,
             shift_cd    = :ls_shift,
             worker_id   = :ls_worker_id,
             update_dt   = getdate()
       WHERE lot_no = :ls_lot_no;

      if SQLCA.SQLCode <> 0 then
        messagebox("오류", "생산실적 수정 실패: " + SQLCA.SQLErrText)
        rollback;
        return
      end if
    end if
  next

  commit;
  messagebox("확인", "저장되었습니다.")
  trigger event open()
end event

event ue_new_lot();
  // 신규 LOT 등록
  string ls_new_lot, ls_plant_cd, ls_line_cd
  ls_plant_cd = f_get_default_plant()
  ls_line_cd  = sle_line.text

  SELECT lot_seq.nextval INTO :ls_new_lot FROM dual;

  INSERT INTO tb_prod_result (lot_no, plant_cd, line_cd, prod_dt, status, create_dt)
  VALUES (:ls_new_lot, :ls_plant_cd, :ls_line_cd, today(), 'NEW', getdate());

  if SQLCA.SQLCode <> 0 then
    messagebox("오류", "LOT 생성 실패: " + SQLCA.SQLErrText)
    rollback;
    return
  end if

  commit;

  // 재고 테이블에 예비 등록
  INSERT INTO tb_inventory (lot_no, plant_cd, wh_cd, stock_qty, stock_weight, inv_status, create_dt)
  VALUES (:ls_new_lot, :ls_plant_cd, 'WH01', 0, 0, 'RESERVED', getdate());

  commit;
  dw_prod_result.retrieve(ls_plant_cd, today())
end event

event ue_delete();
  long ll_row
  string ls_lot_no

  ll_row = dw_prod_result.GetRow()
  if ll_row <= 0 then return

  ls_lot_no = dw_prod_result.GetItemString(ll_row, "lot_no")

  DELETE FROM tb_prod_result WHERE lot_no = :ls_lot_no AND status = 'NEW';

  if SQLCA.SQLCode <> 0 then
    rollback;
    return
  end if

  commit;
  trigger event open()
end event

event ue_open_inventory();
  // 재고조회 화면 호출
  string ls_prod_cd
  long ll_row
  ll_row = dw_prod_result.GetRow()
  if ll_row > 0 then
    ls_prod_cd = dw_prod_result.GetItemString(ll_row, "prod_cd")
    open(w_inventory)
  end if
end event

public function integer f_init_screen();
  // 화면 컨트롤 초기화
  dw_prod_result.Reset()
  ddlb_plant.AddItem("포항")
  ddlb_plant.AddItem("광양")
  return 1
end function

public function string f_get_default_plant();
  string ls_plant
  SELECT plant_cd INTO :ls_plant
    FROM tb_user_config
   WHERE user_id = f_get_user_id()
     AND config_key = 'DEFAULT_PLANT';
  if SQLCA.SQLCode <> 0 then ls_plant = "P01"
  return ls_plant
end function

public function integer f_set_title(string as_title);
  this.title = as_title
  return 1
end function
