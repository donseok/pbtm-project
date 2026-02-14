forward
global type w_inventory from window
end type
end forward

global type w_inventory from window
integer width = 3000
integer height = 2200
string title = "재고 조회"
end type

on w_inventory.create
  call super::create
  trigger event constructor()
end on

event constructor();
  // 재고조회 화면 초기화
  f_init_combo()
  dw_inventory.SetTransObject(SQLCA)
end event

event open();
  string ls_wh_cd, ls_prod_cd
  ls_wh_cd   = ddlb_warehouse.text
  ls_prod_cd = sle_prod_cd.text

  if ls_wh_cd = "" then ls_wh_cd = "WH01"

  dw_inventory.retrieve(ls_wh_cd, ls_prod_cd)
  f_update_summary()
end event

event clicked();
  // 재고 상세: 해당 LOT의 생산실적으로 이동
  long ll_row
  ll_row = dw_inventory.GetClickedRow()

  if ll_row > 0 then
    string ls_lot_no
    ls_lot_no = dw_inventory.GetItemString(ll_row, "lot_no")
    openwithparm(w_prod_result, ls_lot_no)
  end if
end event

event ue_search();
  // 재고 검색 실행
  string ls_wh_cd, ls_prod_cd, ls_grade, ls_inv_status
  date ld_from, ld_to

  ls_wh_cd      = ddlb_warehouse.text
  ls_prod_cd    = sle_prod_cd.text
  ls_grade      = ddlb_grade.text
  ls_inv_status = ddlb_status.text
  ld_from       = date(em_date_from.text)
  ld_to         = date(em_date_to.text)

  dw_inventory.retrieve(ls_wh_cd, ls_prod_cd)
end event

event ue_transfer();
  // 재고 이동 처리 (창고 간)
  long ll_row
  string ls_lot_no, ls_from_wh, ls_to_wh
  decimal ld_transfer_qty, ld_transfer_weight

  ll_row = dw_inventory.GetRow()
  if ll_row <= 0 then
    messagebox("알림", "이동할 재고를 선택하세요.")
    return
  end if

  ls_lot_no = dw_inventory.GetItemString(ll_row, "lot_no")
  ls_from_wh = dw_inventory.GetItemString(ll_row, "wh_cd")
  ls_to_wh = sle_target_wh.text
  ld_transfer_qty = dec(sle_transfer_qty.text)
  ld_transfer_weight = dec(sle_transfer_weight.text)

  // 출고 처리
  UPDATE tb_inventory
     SET stock_qty    = stock_qty - :ld_transfer_qty,
         stock_weight = stock_weight - :ld_transfer_weight,
         update_dt    = getdate()
   WHERE lot_no = :ls_lot_no
     AND wh_cd  = :ls_from_wh;

  if SQLCA.SQLCode <> 0 then
    messagebox("오류", "출고 처리 실패: " + SQLCA.SQLErrText)
    rollback;
    return
  end if

  // 입고 처리
  MERGE INTO tb_inventory t
  USING (SELECT :ls_lot_no AS lot_no, :ls_to_wh AS wh_cd FROM dual) s
     ON (t.lot_no = s.lot_no AND t.wh_cd = s.wh_cd)
   WHEN MATCHED THEN
     UPDATE SET stock_qty    = stock_qty + :ld_transfer_qty,
                stock_weight = stock_weight + :ld_transfer_weight,
                update_dt    = getdate()
   WHEN NOT MATCHED THEN
     INSERT (lot_no, plant_cd, wh_cd, stock_qty, stock_weight, inv_status, create_dt)
     VALUES (:ls_lot_no, 'P01', :ls_to_wh, :ld_transfer_qty, :ld_transfer_weight, 'NORMAL', getdate());

  if SQLCA.SQLCode <> 0 then
    messagebox("오류", "입고 처리 실패: " + SQLCA.SQLErrText)
    rollback;
    return
  end if

  // 이동 이력 기록
  INSERT INTO tb_inv_transfer_hist
    (lot_no, from_wh, to_wh, transfer_qty, transfer_weight, transfer_dt, worker_id)
  VALUES
    (:ls_lot_no, :ls_from_wh, :ls_to_wh, :ld_transfer_qty, :ld_transfer_weight, getdate(), f_get_user_id());

  commit;
  messagebox("확인", "재고 이동이 완료되었습니다.")
  trigger event open()
end event

event ue_export_excel();
  // 엑셀 내보내기
  string ls_filepath
  ls_filepath = "C:\export\inventory_" + string(today(), "yyyymmdd") + ".xlsx"
  dw_inventory.SaveAs(ls_filepath, Excel!, true)
end event

event ue_quality_check();
  // 품질 검사 이력 확인
  long ll_row
  string ls_lot_no

  ll_row = dw_inventory.GetRow()
  if ll_row > 0 then
    ls_lot_no = dw_inventory.GetItemString(ll_row, "lot_no")
    openwithparm(w_quality_inspect, ls_lot_no)
  end if
end event

public function integer f_init_combo();
  // 창고 콤보 초기화
  string ls_wh_cd, ls_wh_nm

  DECLARE cur_wh CURSOR FOR
    SELECT wh_cd, wh_nm FROM tb_warehouse WHERE use_yn = 'Y' ORDER BY wh_cd;

  OPEN cur_wh;
  FETCH cur_wh INTO :ls_wh_cd, :ls_wh_nm;

  do while SQLCA.SQLCode = 0
    ddlb_warehouse.AddItem(ls_wh_cd + " - " + ls_wh_nm)
    FETCH cur_wh INTO :ls_wh_cd, :ls_wh_nm;
  loop

  CLOSE cur_wh;
  return 1
end function

public function integer f_update_summary();
  // 화면 하단 요약 정보 갱신
  decimal ld_total_qty, ld_total_weight
  long ll_count

  SELECT count(*), sum(stock_qty), sum(stock_weight)
    INTO :ll_count, :ld_total_qty, :ld_total_weight
    FROM tb_inventory
   WHERE wh_cd = ddlb_warehouse.text
     AND stock_qty > 0;

  st_summary.text = "건수: " + string(ll_count) + " / 수량: " + string(ld_total_qty, "#,##0") + " / 중량: " + string(ld_total_weight, "#,##0.000") + " ton"
  return 1
end function
