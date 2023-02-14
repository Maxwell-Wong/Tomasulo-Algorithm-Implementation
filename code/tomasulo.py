import os
from queue import Queue
from collections import Counter
from copy import deepcopy
cnt = 1
register_file = []
output_file1 = './output1.txt'
output_file2 = './output2.txt'
output_test = './test.txt'
test1 = '/Users/maxwell/Desktop/Computer Architecture_2022/Homework-5/input1.txt'
test2 = '/Users/maxwell/Desktop/Computer Architecture_2022/Homework-5/input2.txt'   
fu_adder_lock = False  # 加法器资源锁(暂时不用)
fu_mult_lock = False  # 乘法器锁(暂时不用)
constant_reg = ['F4']
operand_from_load = {}
operand_from_load_fu = {} # 保存LD指令对应的load_buffer(FU)
operand_from_load_mult = {} # 保存DIVD/MULT指令对应的RS名字
operand_from_load_add = {} # 保存ADDD/SUBD指令对应的RS名字
stalled_instruction = [] # 保存因为结构冒险而stall的指令
dependency = {} # 保存依赖关系(ID:{rs1:FU, rs2:FU}) or ID:{rt:FU})
dependency_res_status_dict = {} # 保存指令所依赖的RS

################# 在这里选择测例和输出文件 ################
test = test1
output_file = output_file1

'''
===================================================
===============[Some Prerequisites]================
===================================================
(1) Functional units are not pipelined.
(2) No forwarding, results are communicated by the common data bus (CDB). 
(3) Loads require two clock cycle
(4) Issue (IS) and write-back (WB) result stages each require one clock cycle. 
(5) Branch on Not Equal to Zero (BNEZ) instruction requires one clock cycle.
(6) There are 3 load buffer slots and 3 store buffer slots.
(7) There are 3 FP adder and 2 FP multiplier reservation stations, respectively.

----------------------------
FP instruction | EX Cycles
fadd           | 2
fsub           | 2
fmult          | 10
fdiv           | 20
----------------------------

output format
(1) While progressing output 
Cycle_n
Reservation:(busy #yes or no), (address) # for load and store
Reservation:(busy #yes or no), (op), (Vj), (Vk), (Qj), (Qk) # for others
F0(status), F2(status), F4(status),...., F12(status) # for register result status
# where Vj, Vk indicate the existing source operands, Qj,Qk indicate which reservation station will produce
the corresponding source operands(V and Q cannot both be set)              
(2) Algorithm Complete: (Instruction):(Issue cycle),(Exec comp cyclee),(Write result cycle)

'''


def read_ins(filename=None):
    with open(filename, 'r') as f:
      ins = f.readlines()
      ins = [i.rstrip().split() for i in ins]
      return ins



def check_if_full_and_fetch(reservationStation):
    '''
    如果Reservation Station中有空位，那么返回对应的index
    并且返回flag为False表示未满
    :param reservationStation: MultRS或AddRS
    :return: 如果相应的RS未满则返回flag = False和对应的loc表示index
    '''
    flag = True
    loc = None
    for i, res in enumerate(reservationStation):
        if res['occupied'] is False:
            loc = i
            flag = False
            break
    return flag, loc

def check_if_done(reservationStation):
    '''
    检查Reservation Station中是否还有没有执行完毕的指令
    :param reservationStation: MultRS或AddRS
    :return: 如果RS中存在未执行完的指令则返回flag = False
    '''
    flag = True
    for res in reservationStation:
        if res['occupied'] is True:
            flag = False
            break
    return flag

def remove_reservation_station(reservationStation, idx):
    '''
    移除RS中对应index的项
    :param reservationStation: MultRS或AddRS
    :param idx: MultRS或AddRS中项的index
    :return: None
    '''
    reservationStation[idx]['busy'] = reservationStation[idx]['occupied'] = False
    reservationStation[idx]['opcode'] = ''
    reservationStation[idx]['vj'] = reservationStation[idx]['vk'] = ''
    reservationStation[idx]['qj'] = reservationStation[idx]['qk'] = ''
    reservationStation[idx]['instruction'] = None
    reservationStation[idx]['id'] = -1




def print_state_table(cycle, reservationStation_Add,
                 reservationStation_Mult, register_status_dict, load_buffer, store_buffer):
    '''
    打印当前cycle 所有RS的状态
    :param cycle: 当前周期数
    :param reservationStation_Add: AddRS
    :param reservationStation_Mult: MultRS
    :param register_status_dict: Register Result Status
    :param load_buffer: Load RS
    :param store_buffer: Store RS
    :return: None
    '''
    with open(output_file, 'a') as f:
        print('Cycle_'+str(cycle), file=f)

        for i, load_state in enumerate(load_buffer):
            if load_state['busy']:
                print('Load'+str(i+1) + ':Yes,' + load_state['address'] + ';', file=f)
            else:
                print('Load'+str(i+1) + ':No,' + ';', file=f)

        for i, store_state in enumerate(store_buffer):
            if store_state['busy']:
                print('Store'+str(i+1) + ':Yes,' + store_state['address'], store_state['fu']+';', file=f)
            else:
                print('Store'+str(i+1) + ':No,,'+';', file=f)

        for i, add_state in enumerate(reservationStation_Add):
            if add_state['busy']:
                print('Add' + str(i + 1) +  ':Yes,' + add_state['opcode']+ ',' +
                      add_state['vj'] + ',' + add_state['vk'] + ',' +
                      add_state['qj'] + ',' + add_state['qk'] + ';', file=f)

            else:
                print('Add' + str(i + 1) +  ':No,,,,,' + ';', file=f)

        for i, mult_state in enumerate(reservationStation_Mult):
            if mult_state['busy']:
                print('Mult' + str(i + 1) + ':Yes,' +  mult_state['opcode'] + ',' +
                      mult_state['vj'] + ',' + mult_state['vk'] + ',' +
                      mult_state['qj'] + ',' + mult_state['qk'] + ';', file=f)

            else:
                print('Mult' + str(i + 1) + ':No,,,,,' + ';', file=f)

        for k, v in register_status_dict.items():
            val = v
            # 在input1中把F4当成了常量寄存器
            if test == test1:
                if k == 'F4':
                    val = ''
            print(k + ':' + val + ';', end='', file=f)
        print('\n', file=f)

def print_final_state(final_state_list):
    '''
    打印最终Instruction Status结果
    :param final_state_list: Instruction Status列表
    :return: None
    '''
    with open(output_file, 'a') as f:
        for state in final_state_list:
            print(state['instruction'] + ':' + str(state['issue_cycle']) + ','
                  + str(state['exec_comp_cycle']) + ',' + str(state['write_result_cycle']) + ';', file=f)
    print('RESULT INSTRUCTION STATUS')
    for state in final_state_list:
        print(state['instruction'] + ':' + str(state['issue_cycle']) + ','
              + str(state['exec_comp_cycle']) + ',' + str(state['write_result_cycle']) + ';')

def tomasulo_alg(instructionQueue, reservationStation_Add,
                 reservationStation_Mult, register_status_dict, load_buffer, store_buffer, final_state_list):
    '''
    
    :param instructionQueue: 指令队列
    :param reservationStation_Add: AddRS
    :param reservationStation_Mult: MultRS
    :param register_status_dict: Register Result Status
    :param load_buffer: LoadRS
    :param store_buffer: StoreRS
    :param final_state_list: Instruction Status列表
    :return: None
    '''
    cycle = 1 
    ins_cnt = 0 # 作为指令编号
    finish = False
    stall_reservationStation_Add = False # AddRS是否Stall
    stall_reservationStation_Mult = False # MultRS是否Stall
    if test == test1:
        register_file['R(F4)F4'] = True

    while not instructionQueue.empty() or not finish and not stall_reservationStation_Add and not stall_reservationStation_Mult:
        ### Issue instruction (FIFO) ###

        # 检测RS是否已满，如果未满且指令队列未空则继续取指令
        occupied_Add, _ = check_if_full_and_fetch(reservationStation_Add)
        occupied_Mult, _ = check_if_full_and_fetch(reservationStation_Mult)

        if not occupied_Add:
            stall_reservationStation_Add = False
        if not occupied_Mult:
            stall_reservationStation_Mult = False


        if not instructionQueue.empty() and not stall_reservationStation_Add and not stall_reservationStation_Mult:
            if len(stalled_instruction) != 0:
                cur_instruction = stalled_instruction[0]
                stalled_instruction.clear()
                ins_cnt -= 1

            else:
                cur_instruction = instructionQueue.get()

            if cur_instruction['opcode'] == 'ADDD' or cur_instruction['opcode'] == 'SUBD':
                occupied, loc = check_if_full_and_fetch(reservationStation_Add)
                if not occupied:
                    reservationStation_Add[loc]['id'] = ins_cnt
                    reservationStation_Add[loc]['instruction'] = cur_instruction
                    reservationStation_Add[loc]['occupied'] = reservationStation_Add[loc]['busy'] = True
                    reservationStation_Add[loc]['opcode'] = cur_instruction['opcode']
                    if register_file[cur_instruction['rs1']]:
                        reservationStation_Add[loc]['vj'] = register_status_dict[cur_instruction['rs1']]
                    else:
                        reservationStation_Add[loc]['qj'] = register_status_dict[cur_instruction['rs1']]

                    if register_file[cur_instruction['rs2']]:
                        reservationStation_Add[loc]['vk'] = register_status_dict[cur_instruction['rs2']]
                    else:
                        reservationStation_Add[loc]['qk'] = register_status_dict[cur_instruction['rs2']]

                    
                    if ins_cnt not in dependency.keys():
                        rs1 = register_status_dict[cur_instruction['rs1']]
                        rs2 = register_status_dict[cur_instruction['rs2']] 

                        if cur_instruction['rs1'] in operand_from_load_fu.keys():
                            rs1 = operand_from_load_fu[cur_instruction['rs1']]
                        if cur_instruction['rs2'] in operand_from_load_fu.keys():
                            rs2 = operand_from_load_fu[cur_instruction['rs2']]

                        if cur_instruction['rs1'] in operand_from_load_mult.keys():
                            rs1 = operand_from_load_mult[cur_instruction['rs1']]
                        if cur_instruction['rs2'] in operand_from_load_mult.keys():
                            rs2 = operand_from_load_mult[cur_instruction['rs2']]

                        if cur_instruction['rs1'] in operand_from_load_add.keys():
                            rs1 = operand_from_load_add[cur_instruction['rs1']]
                        if cur_instruction['rs2'] in operand_from_load_add.keys():
                            rs2 = operand_from_load_add[cur_instruction['rs2']]
                        
                        # 记录该指令依赖
                        dependency[ins_cnt] = {
                            'rs1':rs1,
                            'rs2':rs2
                        }


                    func_unit = 'Add'+str(loc+1)
       
                    register_file[func_unit+cur_instruction['rt']] = False
                    operand_from_load_add[cur_instruction['rt']] = func_unit

                    register_status_dict[cur_instruction['rt']] = func_unit


                    final_state_list[cur_instruction['id']]['issue_cycle'] = cycle

                # 如果Reservation Station是满的
                else:
                    stall_reservationStation_Add = True
                    stalled_instruction.append(cur_instruction)

            if cur_instruction['opcode'] == 'MULTD' or cur_instruction['opcode'] == 'DIVD':
                occupied, loc = check_if_full_and_fetch(reservationStation_Mult)
                if not occupied:
                    reservationStation_Mult[loc]['id'] = ins_cnt
                    reservationStation_Mult[loc]['instruction'] = cur_instruction
                    reservationStation_Mult[loc]['occupied'] = reservationStation_Mult[loc]['busy'] = True
                    reservationStation_Mult[loc]['opcode'] = cur_instruction['opcode']

                    if register_file[cur_instruction['rs1']]:
                        reservationStation_Mult[loc]['vj'] = register_status_dict[cur_instruction['rs1']]
                    else:
                        reservationStation_Mult[loc]['qj'] = register_status_dict[cur_instruction['rs1']]
                    if register_file[cur_instruction['rs2']]:
                        reservationStation_Mult[loc]['vk'] = register_status_dict[cur_instruction['rs2']]
                    else:
                        reservationStation_Mult[loc]['qk'] = register_status_dict[cur_instruction['rs2']]

                    # 记录该指令所依赖的RS
                    # 用于解决数据依赖
                    if ins_cnt not in dependency.keys():
                        rs1 = register_status_dict[cur_instruction['rs1']]
                        rs2 = register_status_dict[cur_instruction['rs2']] 
                        if cur_instruction['rs1'] in operand_from_load_fu.keys():
                            rs1 = operand_from_load_fu[cur_instruction['rs1']]
                        if cur_instruction['rs2'] in operand_from_load_fu.keys():
                            rs2 = operand_from_load_fu[cur_instruction['rs2']]

                        if cur_instruction['rs1'] in operand_from_load_mult.keys():
                            rs1 = operand_from_load_mult[cur_instruction['rs1']]
                        if cur_instruction['rs2'] in operand_from_load_mult.keys():
                            rs2 = operand_from_load_mult[cur_instruction['rs2']]

                        if cur_instruction['rs1'] in operand_from_load_add.keys():
                            rs1 = operand_from_load_add[cur_instruction['rs1']]
                        if cur_instruction['rs2'] in operand_from_load_add.keys():
                            rs2 = operand_from_load_add[cur_instruction['rs2']]

                        # 记录该指令依赖
                        dependency[ins_cnt] = {
                            'rs1':rs1,
                            'rs2':rs2
                        }

                    func_unit = 'Mult' + str(loc + 1)
                    register_file[func_unit+cur_instruction['rt']] = False
                    operand_from_load_mult[cur_instruction['rt']] = func_unit

                    register_status_dict[cur_instruction['rt']] = func_unit

                    final_state_list[cur_instruction['id']]['issue_cycle'] = cycle

                # 如果Reservation Station是满的
                else:
                    stall_reservationStation_Mult = True
                    # 将其放入被stall的指令列表
                    stalled_instruction.append(cur_instruction)


            if cur_instruction['opcode'] == 'LD':
                occupied, loc = check_if_full_and_fetch(load_buffer)
                if not occupied:
                    load_buffer[loc]['id'] = ins_cnt
                    load_buffer[loc]['instruction'] = cur_instruction
                    load_buffer[loc]['occupied'] = load_buffer[loc]['busy'] = True
                    final_state_list[cur_instruction['id']]['issue_cycle'] = cycle
                    op = cur_instruction['rs1']+cur_instruction['rs2']
                    func_unit = 'Load' + str(loc + 1)
                    register_file[func_unit+cur_instruction['rt']] = False
                
                    operand_from_load_fu[cur_instruction['rt']] = func_unit
                    if cur_instruction['rs1'] == '0':
                        op = cur_instruction['rs2']
                    operand_from_load[cur_instruction['rt']] = register_status_dict[cur_instruction['rt']] = func_unit
                    load_buffer[loc]['address'] = op


            if cur_instruction['opcode'] == 'SD':
                occupied, loc = check_if_full_and_fetch(store_buffer)
                if not occupied:
                    store_buffer[loc]['id'] = ins_cnt
                    store_buffer[loc]['instruction'] = cur_instruction
                    store_buffer[loc]['occupied'] = store_buffer[loc]['busy'] = True
                    store_buffer[loc]['fu'] = register_status_dict[cur_instruction['rt']]
                    final_state_list[cur_instruction['id']]['issue_cycle'] = cycle
                    if ins_cnt not in dependency.keys():
                            dependency[ins_cnt] = {
                            'rt':register_status_dict[cur_instruction['rt']],
                           
                        }

            ins_cnt += 1


       ### Execute instructions ###
        for i, load_ins in enumerate(load_buffer):
            if load_ins['busy']:
                if final_state_list[load_ins['id']]['issue_cycle'] + 2 == cycle:
                    final_state_list[load_ins['id']]['exec_comp_cycle'] = cycle

                # Write Back
                if final_state_list[load_ins['id']]['exec_comp_cycle'] != '' \
                        and final_state_list[load_ins['id']]['exec_comp_cycle'] + 1 == cycle:

                    op = 'M(' + load_ins['instruction']['rs1'] +  load_ins['instruction']['rs2'] + ')'
                    if load_ins['instruction']['rs1'] == '0':
                        op = 'M(' + load_ins['instruction']['rs2'] + ')'
                    register_status_dict[load_ins['instruction']['rt']] = \
                        operand_from_load[load_ins['instruction']['rt']] = op
                    final_state_list[load_ins['id']]['write_result_cycle'] = cycle
                
                    func_unit = 'Load' + str(i + 1)
                    register_file[func_unit+load_ins['instruction']['rt']] = True
                    # 清除表项
                    load_ins['busy'] = load_ins['occupied'] = False
                    load_ins['address'] = ''
                    load_ins['id'] = -1

        
        for i, res_add in enumerate(reservationStation_Add):
            # 在每一个cycle都检查处于busy状态的指令需要的操作数是否已经Ready
            if res_add['busy']:
                if res_add['id'] in dependency.keys():
                    rs1_reg = dependency[res_add['id']]['rs1'] + res_add['instruction']['rs1'] # FU + 源寄存器1
                        
                    if register_file[rs1_reg]:  # 若源操作数rs1已经被写入寄存器堆
                        res_add['qj'] = ''
                        res_add['vj'] = register_status_dict[res_add['instruction']['rs1']]
                else:
                    if register_status_dict[res_add['instruction']['rs1']] != '':
                        res_add['qj'] = register_status_dict[res_add['instruction']['rs1']]

                if res_add['id'] in dependency.keys():
                    rs2_reg = dependency[res_add['id']]['rs2'] + res_add['instruction']['rs2'] # FU + 源寄存器2
                    if register_file[rs2_reg]:  # 若源操作数rs2已经被写入寄存器堆
                        res_add['qk'] = ''
                        res_add['vk'] = register_status_dict[res_add['instruction']['rs2']]

                else:
                    if register_status_dict[res_add['instruction']['rs2']] != '':
                        res_add['qk'] = register_status_dict[res_add['instruction']['rs2']]

                # 如果两个源操作数都已经Ready，那么可以进入EX Stage, add, sub都需要2个cycle来执行
                if res_add['vj'] != '' and res_add['vk'] != '' and final_state_list[res_add['id']]['exec_comp_cycle'] == '':
                    final_state_list[res_add['id']]['exec_comp_cycle'] = cycle + 2

                # Write Back, update FU
                if final_state_list[res_add['id']]['exec_comp_cycle'] != '' and \
                        final_state_list[res_add['id']]['exec_comp_cycle'] + 1 == cycle:
                    final_state_list[res_add['id']]['write_result_cycle'] = cycle
                 

                    func_unit = 'Add' + str(i + 1)
                    rt = func_unit+res_add['instruction']['rt']
     
                    register_file[rt] = True

                    op1 = register_status_dict[res_add['instruction']['rs1']]
                    op2 = register_status_dict[res_add['instruction']['rs2']]
                    if res_add['instruction']['rs1'] in operand_from_load.keys():
                        op1 = operand_from_load[res_add['instruction']['rs1']]
                    if res_add['instruction']['rs2'] in operand_from_load.keys():
                        op2 = operand_from_load[res_add['instruction']['rs2']]

                    if res_add['opcode'] == "SUBD":
                        register_status_dict[res_add['instruction']['rt']] = \
                            op1 + '-' + op2
                        if res_add['instruction']['rt'] not in dependency_res_status_dict.keys():
                            dependency_res_status_dict[rt] = op1 + '-' + op2

                    else:
                        register_status_dict[res_add['instruction']['rt']] = \
                            op1 + '+' + op2
                        if res_add['instruction']['rt'] not in dependency_res_status_dict.keys():
                            dependency_res_status_dict[rt] = op1 + '+' + op2

               
                    remove_reservation_station(reservationStation_Add, i)


        for i, res_mult in enumerate(reservationStation_Mult):
            if res_mult['busy']:
                if res_mult['id'] in dependency.keys():
                    rs1_reg = dependency[res_mult['id']]['rs1']+res_mult['instruction']['rs1'] # FU + 源寄存器1
                    if register_file[rs1_reg]:  # 若源操作数rs1已经被写入寄存器堆
                        res_mult['qj'] = ''
                        res_mult['vj'] = register_status_dict[res_mult['instruction']['rs1']]
                        if rs1_reg in dependency_res_status_dict.keys():
                            res_mult['vj'] = dependency_res_status_dict[rs1_reg] # 结果状态避免被其他写相同寄存器的指令覆盖

                else:
                    if register_status_dict[res_mult['instruction']['rs1']] != '':
                        res_mult['qj'] = register_status_dict[res_mult['instruction']['rs1']]

                if res_mult['id'] in dependency.keys():
                    rs2_reg = dependency[res_mult['id']]['rs2']+res_mult['instruction']['rs2'] # FU + 源寄存器2

                    if register_file[rs2_reg]:  # 若源操作数rs2已经被写入寄存器堆
                
                        res_mult['qk'] = ''
                        res_mult['vk'] = register_status_dict[res_mult['instruction']['rs2']]

                else:
                    if register_status_dict[res_mult['instruction']['rs2']] != '':
                        res_mult['qk'] = register_status_dict[res_mult['instruction']['rs2']]

                # mult需要10个cycle, div需要20个cycle
                if res_mult['vj'] != '' and res_mult['vk'] != '' and final_state_list[res_mult['id']]['exec_comp_cycle'] == '':
                    if res_mult['opcode'] == 'MULTD':
                        final_state_list[res_mult['id']]['exec_comp_cycle'] = cycle + 10
                    else:
                        final_state_list[res_mult['id']]['exec_comp_cycle'] = cycle + 20

                # Write Back
                if final_state_list[res_mult['id']]['exec_comp_cycle'] != '' and \
                        final_state_list[res_mult['id']]['exec_comp_cycle'] + 1 == cycle:
                    final_state_list[res_mult['id']]['write_result_cycle'] = cycle
                 
                    func_unit = 'Mult' + str(i + 1)
                    register_file[func_unit+res_mult['instruction']['rt']] = True

                    op1 = register_status_dict[res_mult['instruction']['rs1']]
                    op2 = register_status_dict[res_mult['instruction']['rs2']]
                    if res_mult['instruction']['rs1'] in operand_from_load.keys():
                        op1 = operand_from_load[res_mult['instruction']['rs1']]
                    if res_mult['instruction']['rs2'] in operand_from_load.keys():
                        op2 = operand_from_load[res_mult['instruction']['rs2']]

                    if res_mult['opcode'] == "MULTD":
                        register_status_dict[res_mult['instruction']['rt']] = op1 + '*' + op2
                    else:
                        register_status_dict[res_mult['instruction']['rt']] = op1 + '/' + op2

                    remove_reservation_station(reservationStation_Mult, i)


        for i, store_ins in enumerate(store_buffer):
            if store_ins['busy']:
                if store_ins['id'] in dependency.keys():
                    # Write Back
                    rt_reg = dependency[store_ins['id']]['rt'] + store_ins['instruction']['rt']# FU + 目的寄存器
                    if register_file[rt_reg]:  # 若目的寄存器rt已经被写入寄存器堆
                        final_state_list[store_ins['id']]['exec_comp_cycle'] = cycle + 2
                        register_file[rt_reg] = False # 这里置成False,表示已经取到rt且避免因为下一个周期又将EX Comp的值再增加2

                    if final_state_list[store_ins['id']]['exec_comp_cycle'] != '' and \
                    final_state_list[store_ins['id']]['exec_comp_cycle'] + 1 == cycle:
                        final_state_list[store_ins['id']]['write_result_cycle'] = cycle
                        # 清除表项
                        store_ins['busy'] = store_ins['occupied'] = False
                        store_ins['address'] = ''
                        store_ins['fu'] = ''
                        store_ins['id'] = -1
                   


        print_state_table(cycle, reservationStation_Add,
                 reservationStation_Mult, register_status_dict, load_buffer, store_buffer)
    
        cycle += 1


        # if all works done
        done1 = check_if_done(reservationStation_Add)
        done2 = check_if_done(reservationStation_Mult)
        done3 = check_if_done(load_buffer)
        done4 = check_if_done(store_buffer)
        
        if done1 and done2 and done3 and done4 is True:
            finish = True
        else:
            finish = False


if __name__ == '__main__':
    # Hyper-parameters
    size_of_reservationStation_Add = 3
    size_of_reservationStation_Mult = 2
    size_of_register_status_list = 5
    size_of_load_buffer = 3
    size_of_store_buffer = 3

    # 字典items
    item_of_reservationStation = {
        'id': -1,
        'instruction': None,
        'occupied': False,
        'busy': False,
        'opcode': '',
        'vj': '',
        'vk': '',
        'qj': '',
        'qk': ''
    }

    item_of_load_buffer = {
        'id': -1,
        'instruction': None,
        'occupied': False,
        'busy': False,
        'address':''
    }

    item_of_store_buffer = {
        'id': -1,
        'instruction': None,
        'occupied': False,
        'busy': False,
        'address': '',
        'fu': ''
    }

    final_state = {
        'instruction': '',
        'issue_cycle': -1,
        'exec_comp_cycle': '',
        'write_result_cycle': ''
    }

    instructionQueue = Queue()
    reservationStation_Add = [deepcopy(item_of_reservationStation) for _ in range(size_of_reservationStation_Add)]
    reservationStation_Mult = [deepcopy(item_of_reservationStation) for _ in range(size_of_reservationStation_Mult)]
    register_status_dict = {'F'+str(i*2): '' for i in range(size_of_register_status_list)}
    register_file = {'F'+str(i*2): False for i in range(size_of_register_status_list)}

    if test == test1:
        register_status_dict['F4'] = 'R(F4)'   # 在input1中把F4当成了常量寄存器
        register_file['F4'] = True

    load_buffer = [deepcopy(item_of_load_buffer) for _ in range(size_of_load_buffer)]
    store_buffer = [deepcopy(item_of_store_buffer) for _ in range(size_of_store_buffer)]

    # Read Instructions Here
    instructionList = read_ins(test)
    final_state_list = [deepcopy(final_state) for _ in range(len(instructionList))]


    print('Tomasulo\'s algorithm dynamically scheduling the following %d instructions:' %(len(instructionList)))
    for i, ins in enumerate(instructionList):
        ins_dict = {
            'id': i,
            'opcode': ins[0],
            'rt': ins[1],
            'rs1': ins[2],
            'rs2': ins[3]
        }
        instructionQueue.put(ins_dict)
        instruction = ' '.join(ins)
        final_state_list[i]['instruction'] = instruction
        print('(' + str(cnt) + ') ' + instruction)

        cnt += 1

    print('============================================\n')
    with open(output_file, 'w') as f:
        pass

    # 算法执行
    tomasulo_alg(instructionQueue, reservationStation_Add, reservationStation_Mult,
                 register_status_dict, load_buffer, store_buffer, final_state_list)

    # 打印最终结果
    print_final_state(final_state_list)


