exp = 1,2,3,4

def filter_odd(exp):
    for item in exp:
        if item % 2 == 1:
            yield item

fil = list(filter_odd(exp))
print(f'fil={fil}')

def transfer_odd(exp):
    for item in exp:
        if item % 2 == 1:
            yield item+1
        else:
            yield item

tra = list(transfer_odd(exp))
print(f'tra={tra}')

fil_dir = [item for item in exp if item % 2 == 1]
print(f'fil_dir={fil_dir}')

tra_dir = [item+1 if item%2==1 else item for item in exp]
print(f'tra_dir={tra_dir}')

fil_lazy = (item for item in exp if item % 2 == 1)
print(f'fil_lazy={list(fil_lazy)}')

tra_lazy = (item+1 if item%2==1 else item for item in exp)
print(f'tra_lazy={list(tra_lazy)}')
