event clicked
function integer f_calc(integer ai_value)
open(w_detail)
trigger event clicked
string ls_sql
ls_sql = "select * from tb_order where order_id = :ai_value;"
ls_sql = "insert into tb_order_hist(order_id) values (:ai_value);"
dw_order.retrieve()
